import re
import logging
import os

from src.abstract_fetch import AbstractDataFetcher
from src.exceptions import NoDataError

path_re = re.compile(r"(.*)/(.*)")


class FetchReads(AbstractDataFetcher):
    ENA_PORTAL_BASE_API_URL = "https://www.ebi.ac.uk/ena/portal/api/search?"

    ENA_PORTAL_FIELDS = [
        "study_accession",
        "secondary_study_accession",
        "sample_accession",
        "secondary_sample_accession",
        "experiment_accession",
        "run_accession",
        "instrument_model",
        "library_layout",
        "fastq_ftp",
        "fastq_md5",
        "submitted_ftp",
        "submitted_md5",
        "library_strategy",
        "broker_name",
        "library_source",
    ]

    ENA_PORTAL_RUN_FIELDS = "secondary_study_accession"

    ENA_PORTAL_PARAMS = [
        "dataPortal=metagenome",
        "dccDataOnly=false",
        "result=read_run",
        "format=json",
        "download=true",
        "fields=",
    ]

    # query
    ENA_PORTAL_QUERY = "query=secondary_study_accession=%22{0}%22&"
    ENA_PORTAL_RUN_QUERY = "query=run_accession=%22{0}%22"

    ENA_PORTAL_API_URL = (
        ENA_PORTAL_BASE_API_URL
        + "&".join(ENA_PORTAL_PARAMS)
        + ",".join(ENA_PORTAL_FIELDS)
        + "&"
        + ENA_PORTAL_QUERY
    )
    ENA_PORTAL_API_BY_RUN = (
        ENA_PORTAL_BASE_API_URL
        + "&".join(ENA_PORTAL_PARAMS)
        + ENA_PORTAL_RUN_FIELDS
        + "&"
        + ENA_PORTAL_RUN_QUERY
    )

    def __init__(self, argv=None):
        self.runs = None
        self.ACCESSION_FIELD = "RUN_ID"
        super().__init__(argv)

    @staticmethod
    def add_arguments(parser):
        runs_group = parser.add_mutually_exclusive_group()
        runs_group.add_argument(
            "-ru",
            "--runs",
            nargs="+",
            help="Run accession(s), whitespace separated. Use to download only certain project runs",
        )
        runs_group.add_argument(
            "--run-list", help="File containing line-separated run accessions"
        )
        return parser

    def _validate_args(self):
        if not any(
            [
                self.args.runs,
                self.args.run_list,
                self.args.projects,
                self.args.project_list,
            ]
        ):
            raise ValueError(
                "No data specified, please use -ru, --run-list, -p or --project-list"
            )

    def _process_additional_args(self):
        if self.args.run_list:
            self.runs = self._read_line_sep_file(self.args.run_list)
        else:
            self.runs = self.args.runs

        if not self.args.projects and not self.args.project_list:
            logging.info("Fetching projects from list of runs")
            self.args.projects = self._get_project_accessions_from_runs(self.runs)

    def _retrieve_project_info_from_api(self, project_accession):
        raise_error = (
            False if len(self.projects) > 1 else True
        )  # allows script to continue to next project if one fails
        data = self._retrieve_ena_url(
            self.ENA_PORTAL_API_URL.format(project_accession), raise_on_204=raise_error
        )
        if not data:
            return
        logging.info(
            "Retrieved {count} runs for study {project_accession} from "
            "the ENA Portal API.".format(
                count=len(data), project_accession=project_accession
            )
        )
        mapped_data = []
        for d in data:
            if not d["fastq_ftp"]:
                logging.info(
                    "The generated ftp location for assembly {} is not available yet".format(
                        d["run_accession"]
                    )
                )
            else:
                is_submitted_file = bool(d.get("submitted_ftp"))
                file_paths = d.get("fastq_ftp")  # or rundata.get('submitted_ftp')??
                is_valid_filetype = [
                    self._is_rawdata_filetype(os.path.basename(f))
                    for f in file_paths.split(";")
                ]  # filter filenames not fasta/fastq
                if False not in is_valid_filetype:
                    md5s = d.get("fastq_md5") or d.get("submitted_md5")
                    raw_data_file_path, file_, md5_ = self._get_raw_filenames(
                        d.get("fastq_ftp"),
                        md5s,
                        d.get("run_accession"),
                        is_submitted_file,
                    )
                    mapped_data.append(
                        {
                            "STUDY_ID": d.get("secondary_study_accession"),
                            "SAMPLE_ID": d.get("secondary_sample_accession"),
                            "RUN_ID": d.get("run_accession"),
                            "DATA_FILE_ROLE": "SUBMISSION_FILE"
                            if is_submitted_file
                            else "GENERATED_FILE",
                            "DATA_FILE_PATH": raw_data_file_path,
                            "file": file_,
                            "MD5": md5_,
                            "LIBRARY_STRATEGY": d.get("library_strategy"),
                            "LIBRARY_SOURCE": d.get("library_source"),
                            "LIBRARY_LAYOUT": d.get("library_layout"),
                        }
                    )
        return mapped_data

    def _filter_accessions_from_args(self, run_data, run_accession_field):
        if self.runs:
            run_data = list(
                filter(lambda r: r[run_accession_field] in self.runs, run_data)
            )
        return run_data

    def map_project_info_to_row(self, run):
        return {
            "study_id": run["STUDY_ID"],
            "sample_id": run["SAMPLE_ID"],
            "run_id": run["RUN_ID"],
            "library_layout": run["LIBRARY_LAYOUT"],
            "file": run["file"],
            "file_path": run["DATA_FILE_PATH"],
            "library_strategy": run["LIBRARY_STRATEGY"],
            "library_source": run["LIBRARY_SOURCE"],
        }

    def _get_project_accessions_from_runs(self, runs):
        project_list = set()
        for run in runs:
            data = self._retrieve_ena_url(
                self.ENA_PORTAL_API_BY_RUN.format(run), raise_on_204=False
            )
            if data:
                [project_list.add(d["secondary_study_accession"]) for d in data]
        if not len(project_list):
            raise NoDataError(self.NO_DATA_MSG)
        return project_list


def main():
    data_fetcher = FetchReads()
    data_fetcher.fetch()


if __name__ == "__main__":
    main()

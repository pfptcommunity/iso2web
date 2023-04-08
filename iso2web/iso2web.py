#
# encoding = utf-8
#
import os.path
import sys
import argparse
import logging
from logging import Logger
from typing import Dict
from requests import Session
from datetime import datetime, timedelta, timezone
import dateutil.parser
import math

ISO_URL_INFO = {'WEB': {'URL': 'https://proofpointisolation.com/api/v2/reporting/usage-data'},
                'URL': {'URL': 'https://urlisolation.com/api/v2/reporting/usage-data'}}


def get_script_version() -> str:
    return '0.1.0'


def get_app_name() -> str:
    return 'isolation_to_webhook'


def get_check_point(file: str) -> str:
    if os.path.isfile(file):
        with open(file, 'r') as check_point_file:
            return check_point_file.read()
    return None


def save_check_point(file: str, value: str):
    with open(file, 'w') as check_point_file:
        check_point_file.write(value)


# Get data chunk for event submission
def make_chunks(data, length):
    for i in range(0, len(data), length):
        yield data[i:i + length]


def collect_events(log: Logger, options: Dict):
    # Current log level
    loglevel = logging.getLevelName(log.getEffectiveLevel())
    log.info("Log Level: {}".format(loglevel))

    # Get App Name
    app_name = get_app_name()
    log.info("Application Name: {}".format(app_name))

    # Get the application version
    app_version = get_script_version()
    log.info("Script Version: {}".format(app_version))

    # Get Endpoint Type
    input_type = options.get('input_type')
    log.info("Input Type: {}".format(input_type))

    # User defined input stanza
    identifier = options.get('identifier')
    log.info("Unique Identifier: {}".format(identifier))

    # Checkpoint key for next start date
    checkpoint_file = "{}.checkpoint".format(identifier)
    log.debug("Checkpoint File: {}".format(checkpoint_file))

    # Get checkpoint date value
    checkpoint_data = get_check_point(checkpoint_file)
    log.info("Checkpoint Data: {}".format(checkpoint_data))

    # Get API key
    api_key = options.get('api_key')
    # Logging of API key even in Debug
    log.debug("API Key: {}".format(api_key))

    # Get Page Size
    page_size = options.get('page_size')
    log.debug("Page Size: {}".format(page_size))

    # Get Page Size
    chunk_size = options.get('chunk_size')
    log.debug("Chunk Size: {}".format(chunk_size))

    # Check request timeout
    timeout = float(options.get('timeout'))
    log.debug("HTTP Request Timeout: {}".format(timeout))

    # Callback URL
    callback = options.get('callback')
    log.debug("Callback URL: {}".format(callback))

    # API URL
    url = ISO_URL_INFO[input_type]['URL']
    log.debug("Base URL: {}".format(url))

    # Will be set to start date by either checkpoint or 30days back
    date_start = None

    # Will be set to current date
    date_end = None

    # If not previously excuted
    if checkpoint_data is None:
        current_date = datetime.now(timezone.utc)
        date_end = current_date.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
        date_start = (current_date - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
    else:
        date_end = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
        # Incremental pull from last oldest dataset
        date_start = checkpoint_data

    # Log the current end of the range
    log.info("Start Date: {}".format(date_start))

    # Log the current end of the range
    log.info("End Date: {}".format(date_end))

    # Authentication via Header (AppInspect Fix)
    headers = {'Authorization': 'Bearer {}'.format(api_key)}

    parameters = {"from": date_start, "to": date_end, "pageSize": page_size}

    isolation_data = []

    # Current page
    page = 1

    # Assume at least 1 page
    pages = 1

    # Records processed
    records = 0

    # Used store the most recent date in the dataset processed
    most_recent_datetime = None

    session = Session()

    # Start assuming we have one page but total pages are calcualted in the loop
    while True:
        response = None
        try:
            response = session.get(url, params=parameters, headers=headers, cookies=None, verify=True, cert=None,
                                   timeout=timeout)
        except Exception as e:
            log.error("Call to send_http_request failed: {}".format(e))
            break

        if response.status_code == 200:
            log.debug("Proofpoint Isolation API successfully queried")
        elif response.status_code == 400:
            log.error("Proofpoint Isolation API bad request")
        elif response.status_code == 403 or response.status_code == 401:
            log.error("Proofpoint Isolation API api key invalid")
        else:
            log.error("Proofpoint Isolation API unknown failure [{}]".format(response.status_code))

        # Raise HTTPError exception if we had a failure
        if response.status_code != 200:
            response.raise_for_status()

        r_json = response.json()

        # Since we need the jobID for subsequent requests add it to the request
        # parameters for the next call to the web service.
        if 'jobId' in r_json:
            parameters['jobId'] = r_json['jobId']
            # Log the current jobID
            log.debug("Job ID: {}".format(r_json['jobId']))
        else:
            log.error("Job ID is not defined in the JSON response, exiting")
            break

        # Since we need the pageToken for subsequent requests add it to the
        # request parameters for the next call to the web service.
        if 'pageToken' in r_json:
            parameters['pageToken'] = r_json['pageToken']
            # Log the current pageToken
            log.debug("Page Token: {}".format(r_json['pageToken']))
        else:
            log.debug("Page Token: None")

        # We will only have data once the status is COMPLETED so we poll until
        # our request state is COMPLETED.
        if 'status' in r_json:
            log.debug("Status: {}".format(r_json['status']))
            # According to the API we keep polling with the jobId until
            # the the status is completed.
            if r_json['status'].casefold() != "COMPLETED".casefold():
                log.debug("Polling until status is COMPLETED.")
                continue
        else:
            log.error("Status is not defined in the JSON response, exiting")
            break

        # Total is not a realiable way to determine the number of record pages to read for
        # we really need to read until status == COMPLETED and pageToken == None
        # could be useful information at some point in the future
        if 'total' in r_json:
            log.debug("Total Records: {}".format(r_json['total']))
            pages = math.ceil(int(r_json['total']) / int(page_size))
        else:
            log.debug("Total Records: None")

        # Data contains the total number or records for the current query
        if 'data' in r_json:
            log.info("Data Records: {}".format(len(r_json['data'])))
            if len(r_json['data']) > 0:
                log.info("Page: {} of {}".format(page, pages))
                for entry in r_json['data']:
                    # Collect all data for the current time range
                    isolation_data.append(entry)
            page += 1
        else:
            log.info("Data Records: None")

        # Terminal case for the while loop
        if r_json['status'].casefold() == "COMPLETED".casefold() and 'pageToken' not in r_json:
            break

    if isolation_data:
        # Sort the isolation data by oldest to newest date
        isolation_data_sorted = sorted(isolation_data, key=lambda x: dateutil.parser.parse(x['date']))
        for chunk in make_chunks(isolation_data_sorted, chunk_size):
            # Get last date for the chunk we are processing
            last_processed_entry_date = dateutil.parser.parse(chunk[-1]['date'])
            # Write the single event
            try:
                response = session.post(callback, json=chunk, headers=None, cookies=None,
                                        verify=True, cert=None,
                                        timeout=timeout)
                records += len(chunk)
                next_start_date = last_processed_entry_date + timedelta(seconds=1)
                save_check_point(checkpoint_file, next_start_date.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3])
                log.info("Updating checkpoint [{}] with: {}".format(checkpoint_file, next_start_date.strftime(
                    '%Y-%m-%dT%H:%M:%S.%f')[:-3]))
            except Exception as e:
                log.error("Failed to post data to callback: {}".format(e))
                break

    log.info("Total records processed: {}".format(records))


def main():
    if len(sys.argv) == 1:
        print('iso2web [-h] --endpoint [web|url] ')
        exit(1)

    parser = argparse.ArgumentParser(prog="iso2web",
                                     description="""Tool to send Proofpoint Isolation data to LogRythm""",
                                     formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=80))
    parser.add_argument('-e', '--endpoint', metavar='<web|url>', choices=['WEB', 'URL'], dest="endpoint",
                        type=str.upper, required=True, help='Isolation API endpoint')
    parser.add_argument('-k', '--apikey', metavar='<level>',
                        dest="api_key", type=str, required=True,
                        help='Proofpoint Isolation API Key.')
    parser.add_argument('-i', '--identifier', metavar='<unique_id>', dest="identifier", type=str, required=True,
                        help='Unique identifier associated with the import.')
    parser.add_argument('-t', '--target', metavar='<url>', dest="callback", type=str, required=True,
                        help='Target URL to post the JSON events.')
    parser.add_argument('-l', '--loglevel', metavar='<level>',
                        choices=['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'],
                        dest="loglevel", type=str.upper, required=False,
                        help='Log level to be used critical, error, warning, info or debug.')
    parser.add_argument('-c', '--chunk', metavar='<chunk_size>',
                        dest="chunk_size", type=int, required=False, default=10000, choices=range(1, 10001),
                        help='Number of records processed per event 1 to 10000 (default: 10000)')
    parser.add_argument('--pagesize', metavar='<page_size>',
                        dest="page_size", type=int, required=False, default=10000, choices=range(1, 10001),
                        help='Number of records processed per request 1 to 10000 (default: 10000).')
    parser.add_argument('--timeout', metavar='<timeout>',
                        dest="timeout", type=int, required=False, default=60, choices=range(1, 3601),
                        help="Number of seconds before the web request timeout occurs 1 to 3600 (default: 60)")

    args = parser.parse_args()

    log = logging.getLogger('iso2web')
    log.setLevel('INFO')

    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    stdout_fmt = logging.Formatter('%(message)s')
    stdout_handler.setFormatter(stdout_fmt)

    file_handler = logging.FileHandler("{}.log".format(args.identifier))
    file_fmt = logging.Formatter(
        '%(asctime)s %(levelname)s pid=%(process)d tid=%(threadName)s file=%(filename)s:%(funcName)s:%(lineno)d %(name)s | %(message)s',
        "%Y-%m-%dT%H:%M:%S%z")

    file_handler.setFormatter(file_fmt)

    log.addHandler(stdout_handler)
    log.addHandler(file_handler)

    if args.loglevel:
        log.setLevel(args.loglevel)

    options = dict()
    options['input_type'] = args.endpoint
    options['identifier'] = args.identifier
    options['callback'] = args.callback
    options['chunk_size'] = args.chunk_size
    options['page_size'] = args.page_size
    options['timeout'] = args.timeout
    options['api_key'] = args.api_key

    collect_events(log, options)


# Main entry point of program
if __name__ == '__main__':
    main()

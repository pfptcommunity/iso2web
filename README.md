# Simple Tool to Send Proofpoint Isolation Data to a Webhook

This tool sends Proofpoint Isolation data to a webhook of your choice. 

### Requirements:

* Python 3.9+
 
### Installing the Package
You can install the API library using the following command. 
```
pip install git+https://github.com/pfptcommunity/iso2web.git
```

### Usage

```
usage: iso2web [-h] -e <web|url> -k <level> -i <unique_id> -t <url>
               [-l <level>] [-c <chunk_size>] [--pagesize <page_size>]
               [--timeout <timeout>]

Tool to send Proofpoint Isolation data to LogRythm

optional arguments:
  -h, --help                                show this help message and exit
  -e <web|url>, --endpoint <web|url>        Isolation API endpoint
  -k <level>, --apikey <level>              Proofpoint Isolation API Key.
  -i <unique_id>, --identifier <unique_id>  Unique identifier associated with
                                            the import.
  -t <url>, --target <url>                  Target URL to post the JSON
                                            events.
  -l <level>, --loglevel <level>            Log level to be used critical,
                                            error, warning, info or debug.
  -c <chunk_size>, --chunk <chunk_size>     Number of records posted to the
                                            target per post.
  --pagesize <page_size>                    Number of records processed per
                                            request 1 to 10000.
  --timeout <timeout>                       Number of seconds before the web
                                            request timeout occurs (default:
                                            60)
```

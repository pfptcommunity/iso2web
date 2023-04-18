# Tool to Send Proofpoint Isolation Logs to a Webhook

This tool sends Proofpoint Isolation data to a webhook of your choice. 

### Requirements:

* Python 3.9+
* python-dateutil
* requests
* setuptools
 
### Installing the Package
You can install the API library using the following command. 
```
pip install git+https://github.com/pfptcommunity/iso2web.git
```

### Usage

```
usage: iso2web [-h] {list,delete,run,add} ...

Tool to send Proofpoint Isolation data to LogRythm

optional arguments:
  -h, --help             show this help message and exit

Required Actions:

  {list,delete,run,add}  An action must be specified
```

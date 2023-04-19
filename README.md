# Tool Sends Proofpoint Isolation Logs to a Webhook

This tool sends Proofpoint Isolation data to a webhook of your choice. 

### Requirements:

* Python 3.9+
* python-dateutil
* requests
* cryptography
* setuptools
 
### Installing the Package
You can install the API library using the following command. 
```
pip install git+https://github.com/pfptcommunity/iso2web.git
```
### Use Cases
* SIEM solution without Proofpoint Isolation collector eg. LogRythm
* JSON post to data lake solution

### Usage
```
usage: iso2web [-h] {list,delete,run,add} ...

Tool to send Proofpoint Isolation data to LogRythm

optional arguments:
  -h, --help             show this help message and exit

Required Actions:

  {list,delete,run,add}  An action must be specified
```

#### Creating a new API profile
```
iso2web add -e url -i url_iso_prod -t https://webhook.site -k xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

#### Deleting API profiles
```
iso2web delete -i url_iso_prod
```

#### Running API profiles
```
iso2web run -i url_iso_prod
```

#### Listing all API profiles
```
iso2web list
```

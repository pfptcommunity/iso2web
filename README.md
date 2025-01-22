# Tool Sends Proofpoint Isolation Logs to a Webhook
[![PyPI Downloads](https://static.pepy.tech/badge/iso2web)](https://pepy.tech/projects/iso2web)  
This tool sends Proofpoint Isolation data to a webhook of your choice. 

### Requirements:

* Python 3.9+
* python-dateutil
* requests
* cryptography
* pysocks
 
### Installing the Package

You can install the tool using the following command directly from Github.

```
pip install git+https://github.com/pfptcommunity/iso2web.git
```

or can install the tool using pip.

```
pip install iso2web
```

### Use Cases
* SIEM solution without Proofpoint Isolation collector eg. LogRythm
* JSON post to data lake solution

### Usage
```
usage: iso2web [-h] [--version] {list,delete,run,add} ...

Tool to send Proofpoint Isolation data to LogRythm

optional arguments:
  -h, --help             show this help message and exit
  --version              show the program's version and exit

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
To ignore certificate issues us the --ignore syntax shown below. 
```
iso2web run -i url_iso_prod --ignore
```
#### Listing all API profiles
```
iso2web list
```
#### Basic Data Flow
![Isolation API to Webhook drawio](https://user-images.githubusercontent.com/83429267/235716231-dcd6faa0-bff2-4d14-b23e-31d39d5d8314.png)

### Future
Implement HTTP authentication for webhook callback.

### Limitations

There are currently no known limitations.

For more information please see: https://proofpoint.my.site.com/community/s/article/Proofpoint-Isolation-API-Guide



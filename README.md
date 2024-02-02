# Get-Proxies

<p align="center">
  <img alt="Python3.10+ Only" src="https://img.shields.io/badge/Python_3.10%2B-Only-purple">
  <img alt="GitHub top language" src="https://img.shields.io/github/languages/top/flop-code/get-proxies">
  <img alt="GitHub License" src="https://img.shields.io/github/license/flop-code/get-proxies">
  <img alt="GitHub repo size" src="https://img.shields.io/github/repo-size/flop-code/get-proxies">
</p>


**Get-Proxies** is an open-source, asynchronous, and flexible configuration tool to fetch SOCKS5 proxies and check them with multiple tests.

The program **output format** is compatible with **Proxychains**, so you can quickly find working proxies and use them immediately.

## Usage
### Installing
To start using **Get-Proxies**, you need to clone this repo with:
```sh
git clone https://github.com/flop-code/get-proxies.git
```
*[Optionally create a virtual environment]*

And install requirements with:
```sh
pip install -r requirements.txt
```

### Running
Run the program with:
```sh
python main.py
```

You can also use configuration files (in `.toml` format) to change proxy sources, delays, number of tests and more.

By default, "`config.toml`" is used, but you can change it to your own, by running program with:
```sh
python main.py {path to your config file}
```

### Configuration
To change the configuration you can either edit "`config.toml`" file or create your own (it should be in `.toml` format).

**To get the description of each config parameter, look in [config.toml](config.toml).**

Don't worry, if you skip one of the parameters or write it wrong, the program will warn you.

## How does it work?
The work at all stages is **asynchronous**.

The script fetches proxies from the sources _specified in the config file_, then runs a certain number of tests, with a certain delay between them to filter out non-working proxies.

For example, you can use **2 tests with a delay of 3 minutes** between them, so the first test will weed out the initially non-working servers, and then identify more reliable and durable servers that are ready to work with them.

By the same principle you can use **3 tests with a delay of 1.5 minutes** between them. Accordingly, there will be 3 stages of server screening, and unlike the previous example, there will be fewer servers at the last stage of testing (_if they will stop working during the interval between the 2nd and 3rd test_).
The total test time will be no longer than the last example, but the network load will increase.

**Each individual test works on the principle of sending a request to the HTTP server** (_also specified in the config file_) **through a certain proxy server**, and if the response code is the same as expected (_specified in the config file_), the test will be considered as passed. Otherwise, the proxy will be recognized as not working and will not participate in all subsequent tests.

At the end of all tests, proxies recognized as working will be written to a separate file "`proxies.txt`" in a format ready to be copied into the Proxychains config file.

### Educational purposes only

*The author of the project is not responsible for the consequences of using this tool. Please use the tool and the result of its execution in accordance with the legislation of your country.*

from typing import Any
from sys import argv
from toml import load as toml_load, TomlDecodeError
import asyncio

from colorama import Fore
import aiohttp
from aiohttp_socks import ProxyConnector


class Log:
    @staticmethod
    def inf(msg: str) -> None:
        print(Fore.LIGHTBLACK_EX + "INF\t" + Fore.RESET + msg)

    @staticmethod
    def ok(msg: str) -> None:
        print(Fore.LIGHTGREEN_EX + "OK\t" + Fore.RESET + msg)

    @staticmethod
    def err(msg: str) -> None:
        print(Fore.LIGHTRED_EX + "ERR\t" + Fore.RESET + msg)


class GetProxies:
    def __init__(self,
                 sources: set[str],
                 connection_timeout: int | float,
                 number_of_tests: int,
                 delay_between_tests: int | float,
                 tests_url: str,
                 expected_response_code: int,
                 **kwargs):
        self.sources = sources
        self.connection_timeout = connection_timeout
        self.number_of_tests = number_of_tests
        self.delay_between_tests = delay_between_tests
        self.tests_url = tests_url
        self.expected_response_code = expected_response_code
        self.__dict__.update(kwargs)

    async def fetch_proxies(self) -> set[str]:
        """Fetch proxies from provided sources.
        Returns a set of strings (urls).
        """
        urls = set()

        async with aiohttp.ClientSession() as session:
            for url in self.sources:
                try:
                    async with session.get(url) as response:
                        if response.status < 200 or response.status > 299:
                            continue
                        urls.update((await response.text()).split("\n"))
                except (Exception,):
                    Log.err(f"Error while fetching from \"{url}\".")

        return urls

    async def _test_url(self, url: str) -> tuple[str, bool]:
        """Make requests to the test url.
        Returns a tuple of string (proxy url) and boolean (`True` if proxy has passed all the tests, `False`, if not).
        """
        async with aiohttp.ClientSession(connector=ProxyConnector.from_url("socks5://" + url)) as session:
            for test_number in range(self.number_of_tests):
                try:
                    async with session.get(
                            self.tests_url,
                            timeout=aiohttp.ClientTimeout(connect=self.connection_timeout)
                    ) as response:
                        if response.status == self.expected_response_code:
                            if test_number != self.number_of_tests - 1:
                                await asyncio.sleep(self.delay_between_tests)
                        else:
                            break
                except (Exception,):
                    break
            else:
                return url, True
        return url, False

    async def test_proxies(self, proxies: set[str]) -> set[str]:
        """Test proxies.
        Takes a set of strings (proxy urls).
        Returns a set of strings (urls of proxies, that passed all the tests).
        """
        tasks = [self._test_url(url) for url in proxies]
        results = await asyncio.gather(*tasks)
        return {url for url, passed in results if passed}

    @staticmethod
    async def format_proxies(proxies: set[str]) -> str:
        """Format proxies for Proxychains.
        Takes a set of strings (proxy urls).
        Returns a string of proxies in format for Proxychains.
        """

        proxy_list = []
        for proxy in proxies:
            proxy_list.append("socks5\t" + proxy.replace(":", "\t").expandtabs(17))

        return "\n".join(proxy_list)


class ConfigParser:
    def __init__(self, config_filename: str):
        self.filename = config_filename

        try:
            self._config = toml_load(self.filename)
        except TomlDecodeError:
            Log.err("Error while decoding config file. Exiting.")
            quit(1)

        self.CONFIG_SCHEMA = {
            "io": {"sources": list, "output_filename": str},
            "tests": {"number_of_tests": int, "tests_url": str, "expected_response_code": int,
                      "connection_timeout": (int, float), "delay_between_tests": (int, float)}
        }

    def validate_config(self) -> str | None:
        """Validate config.
        Returns `None` if config is valid, otherwise return string (error message).
        """
        msg_prefix = "Config validation error:"

        for section in self.CONFIG_SCHEMA:
            # Check if section exists.
            if section not in self._config:
                return f"{msg_prefix} No \"[{section}]\" section."

            for key in self.CONFIG_SCHEMA[section]:
                # Check if item exists.
                if key not in self._config[section]:
                    return f"{msg_prefix} No \"{key}\" item in \"[{section}]\" section."

                # Check if item has correct data type.
                if not isinstance(self._config[section][key], self.CONFIG_SCHEMA[section][key]):
                    return f"{msg_prefix} \"{key}\" item in \"[{section}]\" section has wrong data type."

    @property
    def config(self) -> dict[str, Any]:
        return {**self._config["io"], **self._config["tests"]}


async def main(args: list[str]) -> int:
    Log.inf(Fore.LIGHTWHITE_EX + "Welcome to Get-Proxies!")

    config_filename = args[0] if args else "config.toml"
    Log.inf(f"Using config file \"{config_filename}\".\n")

    config_parser = ConfigParser(config_filename)

    validation_message = config_parser.validate_config()
    if validation_message:
        Log.err(validation_message)
        return 1

    get_proxies = GetProxies(**config_parser.config)

    Log.inf("Fetching proxies...")
    proxy_list = await get_proxies.fetch_proxies()
    Log.ok(f"Fetched {len(proxy_list)} proxies.")

    Log.inf("Testing proxies... (This may take some time)")
    proxies = await get_proxies.test_proxies(proxy_list)
    Log.ok(f"Tests completed, {len(proxies)} proxies passed.\n")

    Log.inf("Writing to output file...\n")
    with open(config_parser.config["output_filename"], "w") as output_file:
        output_file.write(await GetProxies.format_proxies(proxies))

    Log.ok("Done.")

    return 0


if __name__ == "__main__":
    try:
        exit(asyncio.run(main(argv[1:])))
    except KeyboardInterrupt:
        Log.inf("Ctrl+C detected. Bye.")

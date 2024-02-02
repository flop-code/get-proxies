from typing import Any
from pprint import pformat
from sys import argv, platform as sys_platform
from time import time
from toml import load as toml_load, TomlDecodeError
from warnings import filterwarnings
import asyncio

from colorama import Fore, init as colorama_init
import aiohttp
from aiohttp_socks import ProxyConnector
colorama_init()


class Log:
    debug_mode = False

    @staticmethod
    def _log(fore: Fore, prefix: str, msg, **kwargs):
        print(fore + (prefix + "\t") + Fore.RESET + str(msg), **kwargs)

    @staticmethod
    def inf(msg, **kwargs) -> None:
        Log._log(Fore.LIGHTBLACK_EX, "INF", msg, **kwargs)

    @staticmethod
    def ok(msg, **kwargs) -> None:
        Log._log(Fore.LIGHTGREEN_EX, "OK", msg, **kwargs)

    @staticmethod
    def wrn(msg, **kwargs) -> None:
        Log._log(Fore.LIGHTYELLOW_EX, "WRN", msg, **kwargs)

    @staticmethod
    def err(msg, **kwargs) -> None:
        Log._log(Fore.LIGHTRED_EX, "ERR", msg, **kwargs)

    @staticmethod
    def dbg(msg, **kwargs) -> None:
        if Log.debug_mode:
            Log._log(Fore.LIGHTWHITE_EX, "DBG", pformat(msg), **kwargs)


class GetProxies:
    def __init__(self,
                 sources: set[str],
                 connection_timeout: int | float,
                 number_of_tests: int,
                 delay_between_tests: int | float,
                 tests_url: str,
                 expected_response_code: int,
                 N_at_once: int,
                 **kwargs):
        self.sources = sources
        self.connection_timeout = connection_timeout
        self.number_of_tests = number_of_tests
        self.delay_between_tests = delay_between_tests
        self.tests_url = tests_url
        self.expected_response_code = expected_response_code
        self.N_at_once = N_at_once
        self.too_many_open_files = False
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
                except OSError as e:
                    if e.errno == 24 and not self.too_many_open_files:
                        Log.err(f"OS Error #24 occurred. Try lowering \"N_at_once\" parameter in your config.")
                        self.too_many_open_files = True
                        return url, False
                    return url, False
                except (Exception,):
                    return url, False
            else:
                return url, True
        return url, False

    async def test_proxies(self, proxies: set[str]) -> set[str]:
        """Test proxies.
        Takes a set of strings (proxy urls).
        Returns a set of strings (urls of proxies, that passed all the tests).
        """
        tasks = [self._test_url(url) for url in proxies]
        results = set()
        started_at = time()
        number_of_blocks = round(len(tasks) / self.N_at_once)

        if self.N_at_once > len(tasks):
            gathered_tasks = await asyncio.gather(*tasks)
            results.update(url for url, passed in gathered_tasks if passed)
            return results

        Log.inf(f"Checking proxies... ~0%, ??? min left", end="\r")
        for block_number, left_index in enumerate(range(0, len(tasks), self.N_at_once), 1):
            gathered_tasks = await asyncio.gather(*tasks[left_index:left_index + self.N_at_once])
            results.update(url for url, passed in gathered_tasks if passed)

            percents = round(block_number * 100 / number_of_blocks, 1)
            blocks_left = number_of_blocks - block_number
            est_time_per_block = (time() - started_at) // block_number
            time_left = blocks_left * est_time_per_block
            Log.inf(f"Checking proxies... ~{percents}%, ~{round(time_left / 60, 2)} min left", end="\r")

        return results

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
            exit(0)

        self.CONFIG_SCHEMA = {
            "io": {"debug_mode": bool, "sources": list, "output_filename": str},
            "tests": {"number_of_tests": int, "tests_url": str, "expected_response_code": int,
                      "connection_timeout": (int, float), "delay_between_tests": (int, float),
                      "N_at_once": int}
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

                # Check if integers are greater than 0.
                if self.CONFIG_SCHEMA[section][key] is int and self._config[section][key] < 0:
                    return f"{msg_prefix} \"{key}\" item in \"[{section}]\" section is integer less than 0."

    @property
    def config(self) -> dict[str, Any]:
        return {**self._config["io"], **self._config["tests"]}


async def main(args: list[str]) -> None:
    Log.inf(Fore.LIGHTWHITE_EX + "Welcome to Get-Proxies!")

    config_filename = args[0] if args else "config.toml"
    Log.inf(f"Using config file \"{config_filename}\".\n")

    config_parser = ConfigParser(config_filename)

    validation_message = config_parser.validate_config()
    if validation_message:
        Log.err(validation_message)
        exit(1)

    cfg = config_parser.config
    Log.debug_mode = cfg["debug_mode"]
    if cfg["N_at_once"] == 0:
        cfg["N_at_once"] = 2**32 - 1
    Log.dbg(cfg)

    get_proxies = GetProxies(**cfg)

    Log.inf("Fetching proxies...")
    proxy_list = await get_proxies.fetch_proxies()
    Log.ok(f"Fetched {len(proxy_list)} proxies.")

    Log.inf("Testing proxies... (This may take some time)")
    proxies = await get_proxies.test_proxies(proxy_list)
    Log.ok(f"Tests completed, {len(proxies)} proxies passed." + " "*12, end="\n\n")

    Log.inf("Writing to output file...\n")
    with open(config_parser.config["output_filename"], "w") as output_file:
        output_file.write(await GetProxies.format_proxies(proxies))

    Log.ok("Done.")


if __name__ == "__main__":
    try:
        if sys_platform in ("win32", "cygwin"):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        asyncio.run(main(argv[1:]))
    except KeyboardInterrupt:
        Log.inf("Ctrl+C detected. Bye." + " "*25)
        filterwarnings("ignore", category=RuntimeWarning)  # Ignore unstarted coroutines.

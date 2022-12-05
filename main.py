"""
waka2readme : WakaTime progress visualizer
=========================================

Wakatime Metrics on your Profile Readme.

Title:
------

```txt
From: 15 February, 2022 - To: 22 February, 2022
````

Byline:
-------

```txt
Total: 34 hrs 43 mins
```

Body:
-----

```txt
Python     27 hrs 29 mins  ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⣀⣀⣀⣀⣀   77.83 %
YAML       2 hrs 14 mins   ⣿⣦⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀   06.33 %
Markdown   1 hr 54 mins    ⣿⣤⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀   05.39 %
TOML       1 hr 48 mins    ⣿⣤⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀   05.11 %
Other      35 mins         ⣦⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀   01.68 %
```

#### Contents = Title + Byline + Body
"""

# standard
from dataclasses import dataclass
from random import SystemRandom
from datetime import datetime
from base64 import b64encode
import logging as logger
from time import sleep
from typing import Any
import sys
import re
import os

# external
# # requests
from requests.exceptions import RequestException
from requests import get as rq_get
# # github
from github import GithubException, Github
# # faker
from faker import Faker


# pylint: disable = logging-fstring-interpolation


################### setup ###################


print()
# hush existing loggers
# pylint: disable = no-member # see: https://stackoverflow.com/q/20965287
for lgr_name in logger.root.manager.loggerDict:
    # to disable log propagation completely set '.propagate = False'
    logger.getLogger(lgr_name).setLevel(logger.WARNING)
# pylint: enable = no-member
# somehow github.Requester gets missed out from loggerDict
logger.getLogger('github.Requester').setLevel(logger.WARNING)
# configure logger
logger.basicConfig(
    datefmt='%Y-%m-%d %H:%M:%S',
    format='[%(asctime)s] ln. %(lineno)-3d %(levelname)-8s %(message)s',
    level=logger.DEBUG
)
try:
    if len(sys.argv) == 2 and sys.argv[1] == '--dev':
        # get env-vars from .env file for development
        from dotenv import load_dotenv
        # comment this out to disable colored logging
        from loguru import logger
        # load from .env before class def gets parsed
        load_dotenv()
except ImportError as im_err:
    logger.warning(im_err)


################### lib-func ###################


def strtobool(val: str | bool) -> bool:
    """
    strtobool
    ---------

        PEP 632 https://www.python.org/dev/peps/pep-0632/ is depreciating distutils.
        This is from the official source code with slight modifications.

    Converts a string representation of truth to True or False.

    - True values are `'y', 'yes', 't', 'true', 'on', and '1'`
    - False values are `'n', 'no', 'f', 'false', 'off', and '0'`
    - Raises `ValueError` if `val` is anything else.
    """
    if isinstance(val, bool):
        return val

    val = val.lower()

    if val in {'y', 'yes', 't', 'true', 'on', '1'}:
        return True

    if val in {'n', 'no', 'f', 'false', 'off', '0'}:
        return False

    raise ValueError(f'invalid truth value for {val}')


################### data ###################


@dataclass(slots=True)
class WakaInput:
    """
    waka2readme Input Env Variables
    ------------------------------
    """
    # constants
    prefix_length: int = 16
    graph_length: int = 25

    # mapped environment variables
    # # required
    gh_token: str | None = os.getenv('INPUT_GH_TOKEN')
    waka_key: str | None = os.getenv('INPUT_WAKATIME_API_KEY')
    api_base_url: str | None = os.getenv(
        'INPUT_API_BASE_URL', 'https://wakatime.com/api'
    )
    repository: str | None = os.getenv('INPUT_REPOSITORY')
    # # depends
    commit_message: str = os.getenv(
        'INPUT_COMMIT_MESSAGE', 'Updated waka2readme graph with new metrics'
    )
    _section_name: str = os.getenv('INPUT_SECTION_NAME', 'waka')
    start_comment: str = f'<!--START_SECTION:{_section_name}-->'
    end_comment: str = f'<!--END_SECTION:{_section_name}-->'
    waka_block_pattern: str = f'{start_comment}[\\s\\S]+{end_comment}'
    # # optional
    show_title: str | bool = os.getenv('INPUT_SHOW_TITLE') or False
    block_style: str = os.getenv('INPUT_BLOCKS', '░▒▓█')
    time_range: str = os.getenv('INPUT_TIME_RANGE', 'last_7_days')
    show_time: str | bool = os.getenv('INPUT_SHOW_TIME') or False
    show_total_time: str | bool = os.getenv('INPUT_SHOW_TOTAL') or False
    show_masked_time: str | bool = os.getenv('INPUT_SHOW_MASKED_TIME') or False

    def validate_input(self) -> bool:
        """
        Validate Input Env Variables
        ----------------------------
        """
        logger.debug('Validating input variables')
        if not self.gh_token or not self.waka_key or not self.api_base_url or not self.repository:
            logger.error('Invalid inputs')
            logger.info('Refer https://github.com/athul/waka-readme')
            return False

        if len(self.commit_message) < 1:
            logger.error(
                'Commit message length must be greater than 1 character long'
            )
            return False

        try:
            self.show_title = strtobool(self.show_title)
            self.show_time = strtobool(self.show_time)
            self.show_total_time = strtobool(self.show_total_time)
            self.show_masked_time = strtobool(self.show_masked_time)
        except ValueError as err:
            logger.error(err)
            return False

        if not self._section_name.isalnum():
            logger.warning('Section name must be in any of [[a-z][A-Z][0-9]]')
            logger.debug('Using default section name: waka')
            self._section_name = 'wakabox'
            self.start_comment = f'<!--START_SECTION:{self._section_name}-->'
            self.end_comment = f'<!--END_SECTION:{self._section_name}-->'
            self.waka_block_pattern = f'{self.start_comment}[\\s\\S]+{self.end_comment}'

        if len(self.block_style) < 2:
            logger.warning('Graph block must be longer than 2 characters')
            logger.debug('Using default blocks: ░▒▓█')
            self.block_style = '░▒▓█'

        if self.time_range not in {
            'last_7_days', 'last_30_days', 'last_6_months', 'last_year', 'all_time'
        }:  # 'all_time' is un-documented, should it be used?
            logger.warning('Invalid time range')
            logger.debug('Using default time range: last_7_days')
            self.time_range = 'last_7_days'

        logger.debug('Input validation complete\n')
        return True


################### logic ###################


def make_title(dawn: str | None, dusk: str | None, /) -> str:
    """
    waka2readme Title
    ----------------

    Makes title for waka2readme.
    """
    logger.debug('Making title')
    if not dawn or not dusk:
        logger.error('Cannot find start/end date\n')
        sys.exit(1)
    api_dfm, msg_dfm = '%Y-%m-%dT%H:%M:%SZ', '%d %B %Y'
    try:
        start_date = datetime.strptime(dawn, api_dfm).strftime(msg_dfm)
        end_date = datetime.strptime(dusk, api_dfm).strftime(msg_dfm)
    except ValueError as err:
        logger.error(f'{err}\n')
        sys.exit(1)

    logger.debug('Title was made\n')
    return f'💬 Languages: From: {start_date} - To: {end_date}'


def make_graph(block_style: str, percent: float, gr_len: int, lg_nm: str = '', /) -> str:
    """
    waka2readme Graph
    ----------------

    Makes time graph from the API's data.
    """
    logger.debug(f'Generating graph for "{lg_nm or "..."}"')
    markers = len(block_style) - 1
    proportion = percent / 100 * gr_len
    graph_bar = block_style[-1] * int(proportion + 0.5 / markers)
    remainder_block = int(
        (proportion - len(graph_bar)) * markers + 0.5
    )
    graph_bar += block_style[remainder_block] if remainder_block > 0 else ''
    graph_bar += block_style[0] * (gr_len - len(graph_bar))

    logger.debug(f'{lg_nm or "..."} graph generated')
    return graph_bar


def prep_content(stats: dict[Any, Any], /) -> str:
    """
    waka2readme Prepare Markdown
    ---------------------------

    Prepared markdown content from the fetched statistics
    ```
    """
    contents = ''

    # Check if any data exists
    if not (lang_info := stats.get('languages')):
        logger.debug('The data seems to be empty, please wait for a day')
        contents += 'No activity tracked'
        return contents

    # make title
    if wk_i.show_title:
        contents += make_title(stats.get('start'), stats.get('end')) + '\n\n'

    # make byline
    if wk_i.show_masked_time and (
        total_time := stats.get('human_readable_total_including_other_language')
    ):
        # overrides 'human_readable_total'
        contents += f'Total Time: {total_time}\n\n'
    elif wk_i.show_total_time and (
        total_time := stats.get('human_readable_total')
    ):
        contents += f'Total Time: {total_time}\n\n'

    # make content
    logger.debug('Making contents')
    pad_len = len(
        # comment if it feels way computationally expensive
        max((l.get('name') for l in lang_info), key=len)
        # and then don't for get to set pad_len to say 13 :)
    )
    for idx, lang in enumerate(lang_info):
        lang_name = lang.get('name')
        # >>> add languages to filter here <<<
        # if lang_name in {...}: continue
        lang_time = lang.get('text') if wk_i.show_time else ''
        lang_ratio = lang.get('percent')
        lang_bar = make_graph(
            wk_i.block_style, lang_ratio, wk_i.graph_length, lang_name
        )
        contents += (
            f'{lang_name.ljust(pad_len)}   ' +
            f'{lang_time: <16}{lang_bar}   ' +
            f'{lang_ratio:.2f}'.zfill(5) + ' %\n'
        )
        if idx >= 5 or lang_name == 'Other':
            break

    logger.debug('Contents were made\n')
    return contents.rstrip('\n')


def fetch_stats() -> dict[Any, Any] | None:
    """
    waka2readme Fetch Stats
    ----------------------

    Returns statistics as JSON string
    """
    attempts = 4
    statistic: dict[str, dict[Any, Any]] = {}
    encoded_key = str(
        b64encode(bytes(str(wk_i.waka_key), 'utf-8')), 'utf-8'
    )
    logger.debug(
        f'Pulling WakaTime stats from {" ".join(wk_i.time_range.split("_"))}'
    )
    while attempts > 0:
        resp_message, fake_ua = '', cryptogenic.choice(
            [str(fake.user_agent()) for _ in range(5)]
        )
        # making a request
        if (resp := rq_get(
            url=f'{str(wk_i.api_base_url).rstrip("/")}/v1/users/current/stats/{wk_i.time_range}',
            headers={
                'Authorization': f'Basic {encoded_key}',
                'User-Agent': fake_ua,
            },
            timeout=30 * (5 - attempts)
        )).status_code != 200:
            resp_message += f' • {conn_info}' if (
                conn_info := resp.json().get("message")
            ) else ''
        logger.debug(
            f'API response #{5 - attempts}: {resp.status_code} • {resp.reason}{resp_message}'
        )
        if resp.status_code == 200 and (statistic := resp.json()):
            logger.debug('Fetched WakaTime statistics')
            break
        logger.debug(f'Retrying in {30 * (5 - attempts )}s ...')
        sleep(30 * (5 - attempts))
        attempts -= 1

    if err := (statistic.get('error') or statistic.get('errors')):
        logger.error(f'{err}\n')
        sys.exit(1)

    print()
    return statistic.get('data')


def churn(old_readme: str, /) -> str | None:
    """
    waka2readme Churn
    ----------------

    Composes WakaTime stats within markdown code snippet
    """
    # getting content
    if not (waka_stats := fetch_stats()):
        logger.error('Unable to fetch data, please rerun workflow\n')
        sys.exit(1)
    # processing content
    try:
        generated_content = prep_content(waka_stats)
    except AttributeError as err:
        logger.error(f'Unable to read API data | {err}\n')
        sys.exit(1)
    print(generated_content, '\n', sep='')
    new_readme = re.sub(
        pattern=wk_i.waka_block_pattern,
        repl=f'{wk_i.start_comment}\n\n```text\n{generated_content}\n```\n\n{wk_i.end_comment}',
        string=old_readme
    )
    if len(sys.argv) == 2 and sys.argv[1] == '--dev':
        logger.debug('Detected run in `dev` mode.')
        # to avoid accidentally writing back to Github
        # when developing and testing waka2readme
        return None

    return None if new_readme == old_readme else new_readme


def genesis() -> None:
    """Run Program"""
    logger.debug('Connecting to GitHub')
    gh_connect = Github(wk_i.gh_token)
    # since a validator is being used casting to string here is okay
    gh_repo = gh_connect.get_repo(str(wk_i.repository))
    readme_file = gh_repo.get_readme()
    logger.debug('Decoding readme contents\n')
    readme_contents = str(readme_file.decoded_content, encoding='utf-8')
    if new_content := churn(readme_contents):
        logger.debug('waka2readme stats has changed')
        gh_repo.update_file(
            path=readme_file.path,
            message=wk_i.commit_message,
            content=new_content,
            sha=readme_file.sha
        )
        logger.info('Stats updated successfully')
        return

    logger.info('waka2readme was not updated')


################### driver ###################


if __name__ == '__main__':
    # faker data preparation
    fake = Faker()
    Faker.seed(0)
    cryptogenic = SystemRandom()

    # initial waka-readme setup
    logger.debug('Initialize waka2readme')
    wk_i = WakaInput()
    if not wk_i.validate_input():
        logger.error('Environment variables are misconfigured\n')
        sys.exit(1)

    # run
    try:
        genesis()
    except KeyboardInterrupt:
        print()
        logger.error('Interrupt signal received\n')
        sys.exit(1)
    except (GithubException, RequestException) as rq_exp:
        logger.critical(f'{rq_exp}\n')
        sys.exit(1)
    print('\nThanks for using waka2readme!\n')

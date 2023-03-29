<a name="top"></a>

<h1 align="center">
  Termcs
</h1>

<h4 align="center">Terminal crypto screener written in Python</h4>

<p align="center">
  <a href="https://pypi.org/project/termcs/">
    <img alt="PyPI" src="https://img.shields.io/pypi/v/termcs">
  </a>
  <a href="https://www.python.org/downloads/">
    <img alt="PyPI - Python Version" src="https://img.shields.io/pypi/pyversions/termcs">
  </a>
  <a href="https://black.readthedocs.io/en/stable/">
    <img alt="Black" src="https://img.shields.io/badge/code_style-black-black">
  </a>
  <a href="https://opensource.org/licenses/MIT">
    <img alt="MIT" src="https://img.shields.io/badge/License-MIT-yellow.svg?style=flat">
  </a>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#install">Install</a> •
  <a href="#usage">Usage</a>
</p>

<p align="center">
  <img align="center" src="https://raw.githubusercontent.com/Riyum/termcs/master/imgs/demo.png" />
</p>

<details>
  <summary>Table of Contents</summary>
  <ol>
    <li><a href="#features">Features</a></li>
    <li><a href="#install">Install</a></li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#table-notation">Table notation</a></li>
    <li><a href="#faq">FAQ</a></li>
    <li><a href="#credits">Credits</a></li>
    <li><a href="#license">License</a></li>
  </ol>
</details>

## Features

* Price and 24H statistics updates for all BUSD/USDT pairs at Binance
  - Choose to show BUSD or USDT or both pairs
  - Price update every 3 seconds
  - Statistics update every 60 seconds
  - UP/DOWN/BEAR/BULL pairs are excluded from the table
* Search the table with regex compatible patterns
* Full/mini table mode
  - When in mini mode only the top and bottom 15 pairs are shown
* Sort the table by a specific column 
* Cross platform
  - Windows, macOS and Linux ready.

<p align="right">(<a href="#top">back to top</a>)</p>

## Requirements

* `python 3.7+`

## Install

```sh
pip install termcs
```

### Run

```sh
termcs
```

<p align="right">(<a href="#top">back to top</a>)</p>

## Usage

To sort the table, simply click on the column header 

### Keybindings

* `f` - Full/mini table
* `/` - Search
* `Esc` - Exit search mode
* `q` - Quit back to the terminal 

#### Pair control

* `b` - Show BUSD pairs only
* `t` - Show USDT pairs only
* `o` - Show both pairs
* `p` - Show/hide pair name

<p align="right">(<a href="#top">back to top</a>)</p>

## Table notation

| Column        | Description                                                                         |
| ------------- | -------------                                                                       |
| Price         | Current price (USD)                                                                 |
| Change        | The difference between the current price and the price 24 hours ago (percentage)    |
| High          | Highest price for the last 24 hours (USD)                                           |
| Low           | Lowest price for the last 24 hours (USD)                                            |
| High Change   | The difference between the current price and the highest 24 hour price (percentage) |
| Low Change    | The difference between the current price and the lowest 24 hour price (percentage)  |
| Volume        | Asset volume for the last 24 hours                                                  |

<p align="right">(<a href="#top">back to top</a>)</p>

## FAQ

#### Q: What's the deal with the update count down ? 

A: An update its when Termcs grabs 24H statistics from Binance and updates the following columns: *Change*, *High*, *Low* & *Volume*.

#### Q: What's determine the asset pair when both pairs are presented in the table ?

A: The pair with the higher volume.

#### Q: Why there is a note "CHANGE PAIR RESTRICTION ENABLED" above the table ?

A: There is a limit of (approx) 27 times you can press the `b` / `t` / `o` keys in one minute, it is done in order to respect the API limit usage and avoid bans

[Read more](https://binance-docs.github.io/apidocs/spot/en/#limits)

<p align="right">(<a href="#top">back to top</a>)</p>

## Credits

This software uses the following open source packages:

- [Textual](https://github.com/Textualize/textual)
- [Binance-connector](https://github.com/binance/binance-connector-python)

## License

MIT

<p align="right">(<a href="#top">back to top</a>)</p>

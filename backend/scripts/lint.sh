#!/usr/bin/env bash

set -e
set -x

mypy app
ruff check --fix app
ruff format app --check

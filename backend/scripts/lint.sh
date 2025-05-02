#!/usr/bin/env bash

set -e
set -x

ruff check --fix app
ruff format app --check
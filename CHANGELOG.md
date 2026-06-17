# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release: clean-room rewrite of `pokemon-ai-agent`
- `pokecore` — pure data: 18×18 type chart, Showdown paste parser, formats, Glicko-2
- `pokeengine` — poke-env wrapper, Showdown protocol parser, runner, end-to-end demo
- `pokellm` — LiteLLM-based agent with 5 tools, prompts, memory, multi-provider
- `pokeapi` — FastAPI + SQLAlchemy + WebSocket + orchestrator
- `pokecli` — CLI client
- Docker Compose deployment (`deploy/docker-compose.yml`)
- OCI ARM systemd installer (`deploy/oci/install.sh`)
- CI: ruff, mypy strict, pytest with coverage gate

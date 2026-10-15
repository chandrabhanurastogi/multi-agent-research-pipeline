# 0007. One validated settings object, read from the environment

- **Status:** Accepted
- **Date:** 2026-10-15
- **Related:** OPS-1, SEC-4, DATA-5; ADR 0004; plan step A1

## Context
Today configuration is read with `os.getenv` in several places and `.env` is loaded by the application. In clusters, configuration comes from ConfigMaps and secrets from Vault (as environment variables or files rendered by Vault Agent).

## Decision
- One `Settings` class (**pydantic-settings**) holds every setting, typed and validated **at startup**; an invalid or missing value stops the process with a clear message.
- Sources: environment variables, plus a secrets directory (`secrets_dir`) for file-mounted Vault secrets. Secrets typed as `SecretStr` so they never print.
- The application **never reads `.env` itself**. Locally, docker-compose passes it (`env_file:`) and `uv run --env-file .env` does the same outside containers.
- `APP_ENV` (`local`, `test`, `dev`, `sit`, `stage`, `prod`) is used only in **validation rules**, never to choose behaviour. Example: the fake LLM is rejected at startup unless `APP_ENV` is `local` or `test`.
- Settings are passed into components (dependency injection), not read globally, so tests construct them directly.

## Alternatives considered
| Option | Why not |
|---|---|
| `os.getenv` + `python-dotenv` (today) | Unvalidated, scattered, `.env` loading hides missing configuration in clusters |
| Config files per environment in the image | Breaks one-image-for-all-environments; secrets risk ending up in the image |

## Consequences
- Every new setting is added in one place, with a type and a default (or explicitly required).
- `.env.example` lists every setting and is checked against `Settings` in a test.

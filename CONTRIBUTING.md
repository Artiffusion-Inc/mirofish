# Contributing Guide

Thank you for your interest in MiroFish-Local! We welcome contributions of any kind.

## How to Submit an Issue

- **Bug Report**: Use the [Bug Report](https://github.com/tt-a1i/MiroFish-local/issues/new?template=bug_report.yml) template
- **Feature Request**: Use the [Feature Request](https://github.com/tt-a1i/MiroFish-local/issues/new?template=feature_request.yml) template

## How to Submit a PR

1. **Fork** this repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Commit your changes: `git commit -m "feat: add your feature"`
4. Push the branch: `git push origin feat/your-feature`
5. Create a **Pull Request**

## Setting Up the Development Environment

Please refer to the "Quick Start" section in [README.md](./README.md) to set up your development environment.

## Code Standards

| Language | Standard | Tool |
|----------|----------|------|
| Python | PEP 8 | `ruff check .` |
| JavaScript | ESLint | `npm run lint` |

## Commit Message Convention

Use the [Conventional Commits](https://www.conventionalcommits.org/) format:

| Prefix | Purpose | Example |
|--------|---------|---------|
| `feat` | New feature | `feat: add graphiti backend support` |
| `fix` | Bug fix | `fix: resolve neo4j connection timeout` |
| `docs` | Documentation update | `docs: update README` |
| `refactor` | Refactoring | `refactor: extract graph storage interface` |
| `test` | Tests | `test: add backend unit tests` |
| `chore` | Build/tooling | `chore: update dependencies` |

## License

By submitting a contribution, you agree to release your code under the same license as this project (AGPL-3.0).

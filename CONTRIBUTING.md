# Contributing to OpenLUTRA

OpenLUTRA is an open-source project published by FastLabel Inc. Thank you for your interest in the project.

> English speakers welcome. Issues and discussions may be written in either Japanese or English.

## Current Stance

| Category | Status |
|---|---|
| **Issues (bug reports / feature requests)** | **Welcome** |
| **Discussions (questions, use-case sharing)** | **Welcome** |
| **Pull Requests (from external contributors)** | **Not accepted at this stage** (see below for the reason) |
| **Security vulnerability reports** | Please follow the procedure in [SECURITY.md](./SECURITY.md) rather than posting a public issue or discussion |

OpenLUTRA is in an early phase. Many aspects of the project — including its design direction, data formats, APIs, UI, and quality-analysis metric definitions — may still change significantly. In order to build a solid foundation through careful internal discussion of these aspects, we are not yet accepting Pull Requests from external contributors. We plan to open up Pull Request submissions once the codebase has stabilized and we have the processes in place to make full use of external contributions.

That said, **reports, suggestions, and questions are always very welcome**. Bug reports, feature requests, use-case sharing, compatibility information around ROS2 / MCAP, and other forms of feedback are all enormously helpful in shaping the direction of the project. Even while direct code contributions via Pull Request are not yet open, we strongly encourage you to engage with the project through Issues and Discussions.

## Filing an Issue

Issues track work that is planned or in progress. We welcome any of the following. Either Japanese or English is fine.

- Bug reports
- Feature requests and use-case proposals
- Unclear or incorrect points in the documentation
- Reports related to ROS2 / MCAP compatibility

Pick a template on the [New Issue](https://github.com/fastlabel/open-lutra/issues/new/choose) page and fill it in — each template asks for exactly the information we need in order to act on the report.

Because OpenLUTRA runs on your own machine alongside your own robot, the environment section of the bug report template is what most investigations hinge on. Please fill it in even when the problem looks unrelated to your setup.

## Asking a Question

Questions about usage, configuration, or expected behavior belong in [Discussions → Q&A](https://github.com/fastlabel/open-lutra/discussions/categories/q-a), not in the issue tracker. An answer there can be marked as accepted, so the next person with the same question finds it.

The Q&A form asks for your version, how you are running OpenLUTRA, and what is publishing your topics — the same environment axes that decide most answers. Please search the existing discussions and check [Troubleshooting in docs/SETUP.md](./docs/SETUP.md#troubleshooting) first.

[Discussions → Show and tell](https://github.com/fastlabel/open-lutra/discussions/categories/show-and-tell) is the place to share your setup, your robot configuration, or anything you built on top of OpenLUTRA.

> **Do not paste your `.env` file into an Issue or a Discussion** — it can contain credentials such as `AWS_ACCESS_KEY_ID`. The templates point at safe alternatives (for example the output of `GET /api/config`), and confidential values should be redacted from any log you attach.

## Plans for when Pull Requests are opened

When we eventually begin accepting Pull Requests, we plan to ask contributors to complete **procedures such as signing a CLA (Contributor License Agreement)** in order to confirm the license grant for each contribution. The exact procedures and wording will be finalized at the time we open up contributions, and this document will be updated accordingly.

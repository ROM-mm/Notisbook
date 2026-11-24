# Security Policy

## Supported Versions

Only the latest published release receives security fixes. Older versions do not receive fixes;
update with `notisbook update` or reinstall using the `install.sh` from the latest release.

| Version  | Supported |
| -------- | --------- |
| 0.10.x   | ✅        |
| < 0.10   | ❌        |

The current version is recorded in [`CHANGELOG.md`](CHANGELOG.md).

## Reporting a Vulnerability

**Do not open a public Issue, Pull Request or Discussion** to report a security vulnerability.

Use GitHub's private vulnerability reporting instead:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Fill in the form with the information described below.

Direct link: <https://github.com/ROM-mm/Notisbook/security/advisories/new>

The report is visible only to you and to the maintainer, @ROM-mm, and the conversation continues through GitHub's
private channel.

## What to Include

- Affected Notisbook version (`notisbook --version` or the installed release).
- macOS version and confirmation that the Mac is Apple silicon.
- Steps to reproduce the issue.
- Expected impact (for example: what an attacker can read, modify or execute).
- Proof of concept, if available.

Do not include real credentials, tokens, personal data or third-party data in the report. Use dummy values.

## What to Expect

Notisbook is maintained by a single person, and reports are handled on a best-effort basis, with no guaranteed
timelines.

- **Acknowledgement:** the goal is to respond within a few business days.
- **Assessment:** the maintainer reviews the report, confirms whether or not it is a vulnerability, and keeps you
  informed through the private channel.
- **Coordinated disclosure:** the fix is published in a new release before the details are disclosed publicly.
  We ask that you do not disclose the vulnerability before then.
- **Credit:** if you wish, you will be credited in the security advisory and in `CHANGELOG.md`.

## Scope

In scope are the components maintained in this repository:

- the Notisbook application (backend and frontend);
- the `install.sh` installer;
- the artifacts published in GitHub releases.

Notisbook runs locally on your Mac: the backend listens only on `127.0.0.1`, with a random token generated on each
startup. Reports showing how to bypass these protections are especially welcome.

Out of scope:

- Vulnerabilities in third-party dependencies (for example, Python libraries, Spark, DuckDB, MinIO or the AWS Glue
  image) should be reported directly to the upstream project. If Notisbook is affected by one of them, let us know
  through the private channel described above.

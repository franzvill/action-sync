# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| latest  | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in ActionSync, please report it responsibly:

1. **Do not** open a public GitHub issue for security vulnerabilities
2. Email the maintainer directly or use GitHub's private vulnerability reporting
3. Include as much detail as possible:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

## Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial assessment**: Within 1 week
- **Fix timeline**: Depends on severity, typically 1-4 weeks

## Security Best Practices for Users

When deploying ActionSync:

- **Never commit `.env` files** - Use `.env.example` as a template
- **Use strong passwords** for `POSTGRES_PASSWORD` and `SECRET_KEY`
- **Keep API keys secure** - Rotate them if exposed
- **Run behind a reverse proxy** with HTTPS in production
- **Keep dependencies updated** - Run `pip install --upgrade -r requirements.txt` regularly

## Scope

This security policy applies to:
- The ActionSync application code
- Docker and deployment configurations
- Documentation that could lead to insecure deployments

Third-party dependencies are outside the scope but we will assist in coordinating disclosure if needed.

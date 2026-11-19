# Account administration

The sidebar identifies the signed-in role: Super Admin Workspace, Administration Workspace, Teacher Workspace or Parent & Family Portal. Branding settings still control the school name and printed report details.

## Navigation

- Administration → Create admin: create an Admin login with an explicit selection of page permissions. New accounts never receive the Super Admin role.
- Administration → User permissions: choose another user. For Admin accounts, select permitted pages. For other roles, their existing class/subject/child scope is retained. Toggle **Allow password resets** to delegate or revoke reset capability.
- Administration → Users & passwords: search all supported account types and reset an authorized account's password. Passwords require 8 characters and a maximum of 72 UTF-8 bytes. Existing sessions are revoked on reset.
- Account menu → My profile: upload or remove a JPG, PNG or WebP photo (3 MB / 16 megapixels maximum). The server validates, crops and re-encodes it as a square PNG in the existing database file store.
- Administration → Mail / SMTP: save the outgoing host, port, STARTTLS or SSL/TLS, username, password and sender. Email stays disabled until configured. The explicit **Send test email** action sends one message to the entered recipient; saving settings never sends mail.

## Permission rules

Existing Admin accounts without explicit settings keep their existing access. Super Admins retain full access. Administrators can grant only permissions they hold and cannot modify their own access or a more privileged administrator. Super Admin page permissions cannot be restricted. Only another Super Admin can reset a Super Admin's password. Delegated Teacher/Parent resets can target Teacher and Parent accounts, never Admin or Super Admin accounts.

Page access is checked on the server for direct page URLs, related mutations, exports, CSV routes, report views and media APIs. The sidebar, account menu and quick-navigation index reflect the same permissions. Restricted administrators receive a simple dashboard and no unrestricted data search, preventing dashboard/search from bypassing page access.

New additive tables are created using the application's existing first-use migration convention:

- `sl_user_access`: page allowlist, reset delegation and session version.
- `sl_security_audit`: actor, target, action and time; passwords are never logged.
- `sl_mail_settings`: SMTP connection and sender configuration.

The SMTP password lives in `.secrets/smtp-password` with file mode `0600`, is excluded from Git, and is never sent back to the browser. Include this private file when moving an existing SMTP configuration to another server. TLS certificates are verified. No external mail provider has been configured automatically.

Tests: `.venv/bin/python -m unittest discover -s tests -v`.

## Parent Trash

All Parents includes per-row actions and current-page bulk selection for administrators who can access that page. Trash suspends the parent login, revokes its sessions and preserves child links. Restore returns the original login state and blocks duplicate active mobile/logins. Permanent deletion is available only for trashed parents; it removes the parent record/login and profile photo, and sets linked students’ parent reference to NULL without deleting students or academic records. Old sessions remain revoked after Restore. Each action requires a styled confirmation and is audited. The operation is transactional for the complete selection. Teachers cannot access parent Trash or perform these mutations.

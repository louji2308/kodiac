# .agents/LESSONS.md: Hard-Won Engineering Lessons

Append-only log of issues that took >30 minutes to diagnose or resolve, along with root causes and preventive rules.

---

### LESSON-0001 · 2026-10-28 · Windows Sandbox File Permissions
- **Symptom:** Sandboxed PowerShell commands failed with `UnauthorizedAccessException` when creating or modifying files in the workspace directory.
- **Root Cause:** Standard AppContainer sandbox SID (`S-1-15-2-1` / `ALL APPLICATION PACKAGES`) lacked explicit FullControl on `C:\Users\LOUJAN B\Kodiac`.
- **Fix:** Granted FullControl via `icacls "C:\Users\LOUJAN B\Kodiac" /grant "*S-1-15-2-1:(OI)(CI)F" /T`.
- **Rule:** When setting up workspace permissions on Windows under sandboxed runners, ensure AppContainer SIDs inherit write access so sandboxed commands run cleanly without permission errors.

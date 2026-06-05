# FastAPI Best Architecture

This context records project-specific language for architecture reviews and follow-up implementation work.

## Language

**User session**:
The authenticated continuity for one user across access tokens, refresh tokens, Redis-backed session state, cached user details, and refresh-cookie handling.
_Avoid_: Token session, login session, online user

**Plugin lifecycle**:
The backend plugin continuity from discovery, required-plugin checks, plugin.toml parsing, settings loading, Redis-backed status, dependency ordering, route injection, hooks, install/uninstall packaging, requirements handling, and changed-state signaling.
_Avoid_: Plugin core, plugin router, plugin hooks

**Resource presence**:
The service-layer continuity from fetching a required resource, deciding whether a falsy value means "not found", and raising the correct not-found error message.
_Avoid_: Manual not-found branch, query guard

**Login captcha challenge**:
The login verification continuity from dynamic login config loading, captcha image generation, Redis-backed captcha storage, captcha key construction, expiry handling, comparison, and one-time consumption.
_Avoid_: Captcha Redis key, login captcha branch

**Email captcha challenge**:
The email verification continuity from code generation, Redis-backed email captcha storage, captcha key construction, expiry-to-template data, email delivery, comparison, and one-time consumption.
_Avoid_: Email captcha Redis key, email captcha branch

**OAuth2 state challenge**:
The OAuth2 continuity from state generation, Redis-backed state payload storage, login-vs-binding intent, user binding metadata, expiry handling, state validation, and one-time consumption.
_Avoid_: OAuth2 state Redis key, callback state branch

**User security gate**:
The login-safety continuity from persisted user status, Redis-backed login failure count, lock-window storage, lock expiry cleanup, dynamic user security config, and lockout error messaging.
_Avoid_: Login failure Redis key, user lock Redis key

**User password policy**:
The password-safety continuity from dynamic user security config, password length bounds, complexity requirements, password hashing, password verification, password history lookup, and recent-password rejection.
_Avoid_: Password utility, password validator

**User password expiry**:
The password-age continuity from dynamic user security config, missing-change-time handling, expiry-day calculation, reminder window calculation, and expired-password authorization errors.
_Avoid_: Password expiry branch, password reminder branch

**User password change**:
The post-password-update continuity from preserving the previous password hash, writing password history, updating the password-changed timestamp, and revoking existing User sessions.
_Avoid_: Password reset cleanup, password history side effect

**Reference integrity**:
The service-layer continuity from accepting related resource IDs, normalizing duplicated IDs, comparing fetched records to requested IDs, and raising the correct not-found error when the relation target set is incomplete.
_Avoid_: Manual ID set comparison, relation existence branch

**Plugin API mounting**:
The plugin routing continuity from extension-plugin API file discovery, API package path matching, target router lookup, configured prefix application, plugin status dependency injection, and public URL compatibility.
_Avoid_: Plugin sys API folder, manual plugin route include

**Plugin feature gateway**:
The optional-plugin capability continuity from core business code requesting plugin-backed email, config, OAuth2, or authorization features without depending on each plugin's internal module layout.
_Avoid_: Optional plugin import, plugin helper, direct plugin service

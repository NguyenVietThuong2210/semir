# SemirPhone — Prompt History

Append-only log of user prompts that drive this project. Newest entry at the bottom.

Format per entry:

```
## YYYY-MM-DD HH:MM — short label
> verbatim user prompt
**Outcome / artifact produced:** ...
```

---

## 2026-04-25 — initial spec (`/speckit-specify`)

> tôi muốn tạo 1 project mới là SemirPhone mục đich là sử dụng trên điện thoại ios/android, gồm chức năng login, page home và cụm chức năng Analytics & Reports như tong hình
> - thiết kế data trên UI của app phải giống concept trên web, đảm bảo không bị vỡ layout, luôn có cơ chế render visualize để bạn có thể review và tôi có thể xem trước
> - SemirPhone sẽ gọi đến server mà tôi deploy SemirDashboard và được upload lên app store/ google play, hãy sử dụng ngôn ngữ có thể adapt được cả 2, và đảm bảo về mặt security
> - hãy tạo 1 file note để lưu lại history câu prompt của tôi trong project
> - luôn thực hiện và review như 1 senior engineer

**Outcome / artifact produced:**
- Branch `003-semir-phone-app` created (via `before_specify` hook)
- Spec dir `specs/003-semir-phone-app/` created
- `spec.md` written: 7 user stories (US1-US7 spanning login → home → 5 analytics pages → charts), 37 functional requirements (auth/permissions/UI parity/render mechanism/security/distribution/prompt-history/testing), 10 success criteria, key entities, assumptions, dependencies, out-of-scope list
- `prompts-history.md` (this file) created — fulfills FR-035
- `checklists/requirements.md` quality checklist created

## 2026-04-25 — spec review & hardening (senior PM + engineer review)

> là một senior PM và engineer, hãy review lại plan
> (corrected: nhầm review spec)
> hãy review spec kỹ lại một lần nữa trước khi qua bước tiếp theo. tôi muốn có thể run một lần tạo được app luôn. có guideline hướng dẫn build và đẩy app lên on air thật rõ ràng và chi tiết

**Outcome / artifact produced:**
- Identified 8 spec gaps blocking "run once → app on store"
- Fixed SC-003: rewritten from "100% live value match" (untestable) to "same API response → same display" (testable via fixture)
- Fixed SC-010: "30 minutes" → "2 hours on clean machine with prerequisites installed"
- Fixed FR-031: added CA/intermediate pinning + backup pin requirement (prevents cert-renewal outage)
- Fixed FR-032/033: clarified snapshot mechanism is framework-dependent, defined in planning; added senior QA review gate
- Added 8 new FRs (FR-038–FR-045): README with onboarding steps, Makefile build targets, app icon + splash, store assets folder, privacy policy requirement, iOS code signing docs, Android keystore docs, DEPLOYMENT.md end-to-end guide
- Promoted backend JSON API from "likely needed" to HARD BLOCKER Sprint 0 in Dependencies
- Added 3 missing assumptions: TLS pin rotation, privacy policy URL, Developer account registration
- Added 3 missing out-of-scope items: crash SDK, i18n, in-app update mechanism
- Added `Build Configuration` as a Key Entity
- Total: spec now has 45 FRs, 10 SCs, 3 additional assumptions, 7 dependencies

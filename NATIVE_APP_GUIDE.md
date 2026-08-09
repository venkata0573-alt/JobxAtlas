# TalentHub — Native App Build Guide (Capacitor)

TalentHub ships as a Progressive Web App **and** as native app shells for the Apple App
Store and Google Play Store using [Capacitor 6](https://capacitorjs.com/).

## What's already wired in

- `@capacitor/core`, `@capacitor/cli`, `@capacitor/android`, `@capacitor/ios`
- `@capacitor/push-notifications` — push on iOS (APNs) & Android (FCM)
- `@capacitor/preferences` — encrypted key/value store for secure tokens
- `/app/frontend/capacitor.config.ts` — bundle id `io.talenthub.app`, app name `TalentHub`

## One-time setup (do this on a Mac + Android Studio machine, not the server)

```bash
cd /app/frontend
yarn build                            # builds the React web app into ./build
npx cap add android                   # generates the Android Studio project
npx cap add ios                       # generates the Xcode project (Mac only)
```

## Every subsequent release

```bash
cd /app/frontend
yarn build
npx cap copy                          # copies the new web build into native projects
npx cap sync                          # re-installs native plugins if they changed

# Android — open in Android Studio, hit Build → Generate Signed Bundle
npx cap open android

# iOS — open in Xcode, select TalentHub target, Product → Archive
npx cap open ios
```

## Push notifications

Add your Firebase `google-services.json` under `android/app/` and enable
Push Notifications capability + APNs Auth Key under iOS "Signing & Capabilities".
The web app already registers device tokens via `@capacitor/push-notifications`;
the backend simply needs a `/api/notifications/subscribe` endpoint (P1 backlog).

## Biometric login (Face ID / fingerprint)

The Preferences plugin stores the encrypted JWT refresh cookie. To gate app-launch
behind Face ID / Touch ID, add `@capacitor-community/biometric-auth` and wrap the
login-hydration step in `AuthContext.jsx` behind a biometric prompt. Docs:
https://github.com/capacitor-community/biometric-auth

## Store listing checklist

- **Bundle id**: `io.talenthub.app`
- **App name**: TalentHub
- **Category**: Business
- **Age rating**: 17+ (business marketplace)
- **Privacy policy URL**: `https://talenthub.io/legal`
- **Screenshots**: capture from the web build at 1290×2796 (iOS), 1080×1920 (Android)
- **Support URL**: `mailto:hello@talenthub.io`

## Live-reload mode (during dev)

Set `CAP_SERVER_URL` before syncing to have the native app load your web-preview URL
instead of the bundled build — handy while iterating:

```bash
CAP_SERVER_URL="https://your-preview.emergentagent.com" npx cap copy && npx cap sync
```

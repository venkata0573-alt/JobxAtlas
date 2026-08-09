import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'io.talenthub.app',
  appName: 'TalentHub',
  webDir: 'build',
  bundledWebRuntime: false,
  ios: {
    scheme: 'TalentHub',
    contentInset: 'automatic',
  },
  android: {
    allowMixedContent: false,
  },
  server: {
    // For dev: point to preview URL so the app loads the live web build.
    // Comment `url` out and run `yarn build && npx cap copy` for a bundled release build.
    url: process.env.CAP_SERVER_URL || undefined,
    androidScheme: 'https',
    cleartext: false,
  },
  plugins: {
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert'],
    },
  },
};

export default config;

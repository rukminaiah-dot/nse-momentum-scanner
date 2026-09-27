import { Platform } from 'react-native';

export async function enableNotifications() {
  if (Platform.OS === 'web') return false;
  const Notifications = await import('expo-notifications');
  const p = await Notifications.requestPermissionsAsync();
  return p.status === 'granted';
}

export async function sendTestNotification() {
  if (Platform.OS === 'web') return;
  const Notifications = await import('expo-notifications');
  await Notifications.scheduleNotificationAsync({
    content: {
      title: 'Positive momentum detected',
      body: 'DEMO1: volume + trend confirmation (paper mode).',
    },
    trigger: null,
  });
}

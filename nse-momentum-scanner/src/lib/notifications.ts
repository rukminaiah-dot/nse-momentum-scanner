import * as Notifications from 'expo-notifications';
Notifications.setNotificationHandler({handleNotification:async()=>({shouldShowAlert:true,shouldPlaySound:true,shouldSetBadge:false})});
export async function enableNotifications(){ const p=await Notifications.requestPermissionsAsync(); return p.status==='granted'; }
export async function sendTestNotification(){ await Notifications.scheduleNotificationAsync({content:{title:'Positive momentum detected',body:'DEMO1: volume + trend confirmation (paper mode).'},trigger:null}); }

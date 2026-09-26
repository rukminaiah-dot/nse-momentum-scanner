import React, {useEffect, useState} from 'react';
import {
  SafeAreaView,
  ScrollView,
  View,
  Text,
  TextInput,
  StyleSheet,
  Pressable,
  Switch,
  ActivityIndicator,
} from 'react-native';
import {StatusBar} from 'expo-status-bar';

import {
  getSignals,
  getUniverse,
  addScrip,
  removeScrip,
} from '../src/lib/api';

import {
  enableNotifications,
  sendTestNotification,
} from '../src/lib/notifications';

export default function Home() {
  const [signals, setSignals] = useState<any[]>([]);
  const [universe, setUniverse] = useState<string[]>([]);
  const [ticker, setTicker] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [notifications, setNotifications] = useState(false);

  async function loadData() {
    try {
      const [signalData, universeData] = await Promise.all([
        getSignals(),
        getUniverse(),
      ]);

      setSignals(signalData);
      setUniverse(universeData);
    } catch (error) {
      console.error(error);
      setMessage('Unable to load scanner data.');
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function handleAdd() {
    if (!ticker.trim()) {
      setMessage('Enter an NSE/BSE ticker first.');
      return;
    }

    try {
      setLoading(true);
      setMessage('');

      const result = await addScrip(ticker);

      setTicker('');
      setMessage(`${result.ticker} added successfully.`);
      await loadData();
    } catch (error) {
      console.error(error);
      setMessage(
        'Unable to add scrip. Check the ticker and try again.'
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleRemove() {
    if (!ticker.trim()) {
      setMessage('Enter the ticker you want to remove.');
      return;
    }

    try {
      setLoading(true);
      setMessage('');

      const result = await removeScrip(ticker);

      setTicker('');
      setMessage(`${result.ticker} removed successfully.`);
      await loadData();
    } catch (error) {
      console.error(error);
      setMessage(
        'Unable to remove scrip. Check the ticker and try again.'
      );
    } finally {
      setLoading(false);
    }
  }

  async function toggle(v: boolean) {
    if (v) {
      const ok = await enableNotifications();
      setNotifications(ok);

      if (ok) {
        await sendTestNotification();
      }
    } else {
      setNotifications(false);
    }
  }

  return (
    <SafeAreaView style={s.safe}>
      <StatusBar style="light" />

      <ScrollView contentContainerStyle={s.page}>
        <Text style={s.brand}>MOMENTUM</Text>

        <Text style={s.title}>NSE/BSE Scanner</Text>

        <Text style={s.sub}>
          Signal-finding dashboard
        </Text>

        <View style={s.row}>
          <View style={s.metric}>
            <Text style={s.mlabel}>Mode</Text>
            <Text style={s.mvalue}>PAPER</Text>
          </View>

          <View style={s.metric}>
            <Text style={s.mlabel}>Universe</Text>
            <Text style={s.mvalue}>
              {universe.length}
            </Text>
          </View>
        </View>

        <Text style={s.section}>
          Manage Scrips
        </Text>

        <View style={s.card}>
          <Text style={s.cardTitle}>
            Add / Remove Scrip
          </Text>

          <Text style={s.muted}>
            Example: RELIANCE.NS or 500325.BO
          </Text>

          <TextInput
            style={s.input}
            value={ticker}
            onChangeText={setTicker}
            placeholder="Enter ticker"
            placeholderTextColor="#718096"
            autoCapitalize="characters"
            autoCorrect={false}
          />

          <View style={s.actionRow}>
            <Pressable
              style={[
                s.actionButton,
                s.addButton,
              ]}
              onPress={handleAdd}
              disabled={loading}
            >
              <Text style={s.addButtonText}>
                Add Scrip
              </Text>
            </Pressable>

            <Pressable
              style={[
                s.actionButton,
                s.removeButton,
              ]}
              onPress={handleRemove}
              disabled={loading}
            >
              <Text style={s.removeButtonText}>
                Remove Scrip
              </Text>
            </Pressable>
          </View>

          {loading && (
            <ActivityIndicator
              style={s.loader}
              size="small"
            />
          )}

          {!!message && (
            <Text style={s.message}>
              {message}
            </Text>
          )}
        </View>

        <View style={s.card}>
          <View style={s.between}>
            <View style={s.flex}>
              <Text style={s.cardTitle}>
                Push alerts
              </Text>

              <Text style={s.muted}>
                Notify only after signal filters agree.
              </Text>
            </View>

            <Switch
              value={notifications}
              onValueChange={toggle}
            />
          </View>
        </View>

        <Text style={s.section}>
          Positive momentum
        </Text>

        {signals.length === 0 && (
          <View style={s.card}>
            <Text style={s.muted}>
              No qualifying momentum signals right now.
            </Text>
          </View>
        )}

        {signals.map(x => (
          <View
            key={x.ticker}
            style={s.card}
          >
            <View style={s.between}>
              <View style={s.flex}>
                <Text style={s.symbol}>
                  {x.ticker}
                </Text>
              </View>

              <View>
                <Text style={s.positive}>
                  +{x.momentum_pct.toFixed(2)}%
                </Text>

                <Text style={s.score}>
                  Score {x.score}/100
                </Text>
              </View>
            </View>

            <Text style={s.price}>
              ₹{x.price.toFixed(2)}
            </Text>

            <Text style={s.reason}>
              {x.reason}
            </Text>

            <Text style={s.meta}>
              RVOL {x.relative_volume.toFixed(1)}× • {x.trend}
            </Text>

            <Text style={s.risk}>
              Invalidation: ₹{x.invalidation}
            </Text>
          </View>
        ))}

        <Pressable
          style={s.button}
          onPress={loadData}
        >
          <Text style={s.buttonText}>
            Refresh Scanner
          </Text>
        </Pressable>

        <Pressable
          style={s.secondaryButton}
          onPress={sendTestNotification}
        >
          <Text style={s.secondaryButtonText}>
            Send test notification
          </Text>
        </Pressable>

        <Text style={s.disclaimer}>
          Observed momentum is not a prediction or buy
          recommendation. Live order execution is disabled.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: '#07111f',
  },

  page: {
    padding: 20,
    paddingBottom: 50,
  },

  brand: {
    color: '#5ee6a8',
    fontWeight: '800',
    letterSpacing: 3,
    marginTop: 8,
  },

  title: {
    color: 'white',
    fontSize: 30,
    fontWeight: '800',
    marginTop: 5,
  },

  sub: {
    color: '#91a0b5',
    marginTop: 5,
    marginBottom: 18,
  },

  row: {
    flexDirection: 'row',
    gap: 12,
  },

  metric: {
    flex: 1,
    backgroundColor: '#101d2e',
    padding: 16,
    borderRadius: 16,
  },

  mlabel: {
    color: '#91a0b5',
  },

  mvalue: {
    color: 'white',
    fontSize: 22,
    fontWeight: '800',
    marginTop: 4,
  },

  section: {
    color: 'white',
    fontSize: 20,
    fontWeight: '800',
    marginTop: 24,
    marginBottom: 10,
  },

  card: {
    backgroundColor: '#101d2e',
    padding: 16,
    borderRadius: 18,
    marginBottom: 12,
  },

  between: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 10,
  },

  flex: {
    flex: 1,
  },

  cardTitle: {
    color: 'white',
    fontSize: 17,
    fontWeight: '700',
  },

  muted: {
    color: '#91a0b5',
    marginTop: 4,
    lineHeight: 19,
  },

  input: {
    backgroundColor: '#07111f',
    color: 'white',
    borderWidth: 1,
    borderColor: '#26384d',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 13,
    fontSize: 16,
    marginTop: 15,
  },

  actionRow: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 12,
  },

  actionButton: {
    flex: 1,
    paddingVertical: 13,
    borderRadius: 12,
    alignItems: 'center',
  },

  addButton: {
    backgroundColor: '#5ee6a8',
  },

  addButtonText: {
    color: '#07111f',
    fontWeight: '800',
  },

  removeButton: {
    borderWidth: 1,
    borderColor: '#f0b66b',
  },

  removeButtonText: {
    color: '#f0b66b',
    fontWeight: '800',
  },

  loader: {
    marginTop: 14,
  },

  message: {
    color: '#d8e1ed',
    marginTop: 14,
    lineHeight: 20,
  },

  symbol: {
    color: 'white',
    fontSize: 20,
    fontWeight: '800',
  },

  positive: {
    color: '#5ee6a8',
    fontWeight: '800',
    fontSize: 18,
    textAlign: 'right',
  },

  score: {
    color: '#91a0b5',
    fontSize: 12,
    textAlign: 'right',
  },

  price: {
    color: 'white',
    fontSize: 26,
    fontWeight: '800',
    marginTop: 15,
  },

  reason: {
    color: '#d8e1ed',
    marginTop: 8,
    lineHeight: 20,
  },

  meta: {
    color: '#5ee6a8',
    marginTop: 10,
    fontWeight: '600',
  },

  risk: {
    color: '#f0b66b',
    marginTop: 8,
  },

  button: {
    backgroundColor: '#5ee6a8',
    padding: 16,
    borderRadius: 15,
    alignItems: 'center',
    marginTop: 8,
  },

  buttonText: {
    color: '#07111f',
    fontWeight: '800',
  },

  secondaryButton: {
    borderWidth: 1,
    borderColor: '#26384d',
    padding: 15,
    borderRadius: 15,
    alignItems: 'center',
    marginTop: 10,
  },

  secondaryButtonText: {
    color: '#d8e1ed',
    fontWeight: '700',
  },

  disclaimer: {
    color: '#718096',
    fontSize: 12,
    lineHeight: 18,
    marginTop: 16,
  },
});

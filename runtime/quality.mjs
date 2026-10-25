// Optional observation adapter. No QQ, files, network, rewriting, or suppression.
import { check, dialogueAct } from '../evidence/source/natural-dialogue.mjs';

export class QualityObserver {
  constructor(config = {}) {
    this.enabled = config.enabled !== false && config.mode !== 'off';
    this.window = Math.max(1, Math.min(50, Number(config.recent_window) || 8));
    this.budget = Math.max(1, Math.min(100, Number(config.maxMessagesPerHook) || 20));
    this.history = new Map();
  }

  inspect(messages, { sessionKey = 'default' } = {}) {
    const original = Array.isArray(messages) ? messages.slice() : [messages];
    if (!this.enabled) return { action: 'PASS', messages: original, flags: [], inspected: 0 };
    try {
      const history = this.history.get(String(sessionKey)) || [];
      const inspected = original.slice(0, this.budget);
      const flags = inspected.flatMap((text, index) => check(String(text ?? ''), history).map(flag => ({ ...flag, index })));
      return { action: flags.length ? 'WARN' : 'PASS', messages: original, flags, inspected: inspected.length };
    } catch {
      return { action: 'PASS', messages: original, flags: [], inspected: 0, observerError: true };
    }
  }

  // The host must call this with only the successfully delivered subset.
  confirmDelivered(sessionKey, deliveredTexts) {
    if (!this.enabled || !Array.isArray(deliveredTexts)) return;
    const key = String(sessionKey);
    const history = this.history.get(key) || [];
    history.push(...deliveredTexts.filter(text => typeof text === 'string' && text.trim()));
    this.history.set(key, history.slice(-this.window));
  }

  clear(sessionKey) {
    if (sessionKey === undefined) this.history.clear();
    else this.history.delete(String(sessionKey));
  }
}

export { check, dialogueAct };

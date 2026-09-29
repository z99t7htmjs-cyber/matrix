/**
 * Read-aloud, using the browser's own text-to-speech (Web Speech API) --
 * no server round trip, no cloned or celebrity voice, just an ordinary
 * system voice with a bit of pitch/rate shaping so ARGUS and MOMUS sound
 * like two different things.
 */

export function voiceAvailable() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

function pickVoice(persona) {
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;
  const byLang = (re) => voices.find((v) => re.test(v.lang));
  // No particular voice is "the" ARGUS or MOMUS voice -- whatever's installed,
  // shaped differently below. British English if there's one, for a bit of formality.
  return byLang(/en-GB/i) || byLang(/en-AU/i) || voices.find((v) => v.lang?.startsWith('en')) || voices[0];
}

let speaking = null;

/** Speak `text` in the given persona's register. Cancels anything already playing. */
export function speak(text, persona = 'argus') {
  if (!voiceAvailable() || !text) return;
  window.speechSynthesis.cancel();
  const utter = new SpeechSynthesisUtterance(text.replace(/\s+/g, ' ').trim());
  const voice = pickVoice(persona);
  if (voice) utter.voice = voice;
  if (persona === 'momus') {
    utter.pitch = 0.8;
    utter.rate = 1.08;
  } else {
    utter.pitch = 1;
    utter.rate = 0.95;
  }
  speaking = utter;
  window.speechSynthesis.speak(utter);
}

export function stopSpeaking() {
  if (voiceAvailable()) window.speechSynthesis.cancel();
  speaking = null;
}

export function isSpeaking() {
  return voiceAvailable() && window.speechSynthesis.speaking;
}

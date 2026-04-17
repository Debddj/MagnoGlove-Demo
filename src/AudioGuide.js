/**
 * AudioGuide.js
 * 
 * Uses the Web Speech API (SpeechSynthesis) to narrate
 * step-by-step instructions for the MagnoGlove simulation.
 * Includes play, pause, mute, and auto-advance through script steps.
 */

export class AudioGuide {
  constructor() {
    this.synth = window.speechSynthesis;
    this.speaking = false;
    this.muted = false;
    this.currentStep = 0;
    this.utterance = null;
    this.onStepChange = null; // callback

    // Narration script — each entry is one spoken segment
    this.script = [
      {
        id: 'welcome',
        text: 'Welcome to MagnoGlove Pro. This is a dual-hand augmented reality electromagnetic simulation. I will guide you through the controls.',
        subtitle: 'Welcome to MagnoGlove Pro — Dual Hand AR Electromagnetic Simulation'
      },
      {
        id: 'hands',
        text: 'First, hold both hands up in front of the camera, about 30 to 80 centimeters away. Make sure the lighting is good so the AI can detect your hands clearly.',
        subtitle: 'Hold both hands up in front of the camera (30–80 cm away)'
      },
      {
        id: 'open',
        text: 'Start with both hands open, fingers spread apart. This is the off state. The magnetic gloves are in standby mode, and the metal objects rest on the surface below.',
        subtitle: '✋ Open hands = Magnets OFF — objects rest naturally'
      },
      {
        id: 'fist',
        text: 'Now, close one hand into a fist. This activates maximum magnetic power. You will see a cyan glow around your hand and the metal objects will fly toward your fist.',
        subtitle: '✊ Close fist = MAX POWER — objects fly toward your hand'
      },
      {
        id: 'pinch',
        text: 'Try pinching your thumb and index finger together. This activates precision mode with lower power and an amber glow. Objects move slowly and gently toward your hand.',
        subtitle: '👌 Pinch = PRECISION mode — gentle pull with amber glow'
      },
      {
        id: 'dual',
        text: 'Now try making fists with both hands simultaneously. Energy arcs will crackle between your palms, and objects will be pulled from both directions. This is dual magnet mode.',
        subtitle: '⚡ Both fists = DUAL MODE — energy arcs between hands'
      },
      {
        id: 'release',
        text: 'Open both hands again to release. The objects will fall back down with realistic gravity and bounce on the surface.',
        subtitle: '✋ Open hands to release — objects fall with gravity'
      },
      {
        id: 'geometry',
        text: 'You can also switch to Geometry Mode using the toggle at the top of the screen. In this mode, your fingertips become measurement points. With two hands visible, a triangle forms between your index fingers and thumb, showing side lengths, angles, and area in real time.',
        subtitle: '📐 Switch to GEOMETRY MODE for real-time shape measurements'
      },
      {
        id: 'circle',
        text: 'In geometry mode with one hand, try pinching your thumb and index finger. A circle appears with the pinch distance as the diameter, showing the radius, circumference, and area.',
        subtitle: '⭕ Pinch with one hand to create a circle measurement'
      },
      {
        id: 'end',
        text: 'That concludes the tutorial. Enjoy experimenting with MagnoGlove Pro! You can replay this guide anytime by clicking the audio button.',
        subtitle: 'Tutorial complete — enjoy MagnoGlove Pro! 🧲⚡'
      }
    ];
  }

  /**
   * Start narrating from the beginning
   */
  start() {
    this.currentStep = 0;
    this.speakCurrent();
  }

  /**
   * Speak the current step
   */
  speakCurrent() {
    if (this.muted || this.currentStep >= this.script.length) {
      this.speaking = false;
      return;
    }

    // Cancel any in-progress speech
    this.synth.cancel();

    const step = this.script[this.currentStep];
    this.utterance = new SpeechSynthesisUtterance(step.text);
    this.utterance.rate = 0.95;
    this.utterance.pitch = 1.0;
    this.utterance.volume = 0.9;

    // Try to pick a good voice
    const voices = this.synth.getVoices();
    const preferred = voices.find(v =>
      v.name.includes('Google') && v.lang.startsWith('en')
    ) || voices.find(v => v.lang.startsWith('en'));
    if (preferred) this.utterance.voice = preferred;

    this.utterance.onstart = () => {
      this.speaking = true;
      if (this.onStepChange) this.onStepChange(step, this.currentStep);
    };

    this.utterance.onend = () => {
      this.currentStep++;
      // Small pause between steps
      setTimeout(() => this.speakCurrent(), 800);
    };

    this.utterance.onerror = (e) => {
      console.warn('[AudioGuide] Speech error:', e.error);
      this.speaking = false;
    };

    this.synth.speak(this.utterance);
  }

  /**
   * Toggle mute / unmute
   */
  toggleMute() {
    this.muted = !this.muted;
    if (this.muted) {
      this.synth.cancel();
      this.speaking = false;
    } else if (this.currentStep < this.script.length) {
      this.speakCurrent();
    }
    return this.muted;
  }

  /**
   * Stop and reset
   */
  stop() {
    this.synth.cancel();
    this.speaking = false;
    this.currentStep = 0;
  }

  /**
   * Skip to next step
   */
  next() {
    this.synth.cancel();
    this.currentStep++;
    if (this.currentStep < this.script.length) {
      this.speakCurrent();
    } else {
      this.speaking = false;
    }
  }

  /**
   * Get current subtitle text for display
   */
  getCurrentSubtitle() {
    if (!this.speaking || this.currentStep >= this.script.length) return null;
    return this.script[this.currentStep].subtitle;
  }

  isSpeaking() { return this.speaking; }
  isMuted() { return this.muted; }
  getProgress() {
    return `${Math.min(this.currentStep + 1, this.script.length)} / ${this.script.length}`;
  }
}

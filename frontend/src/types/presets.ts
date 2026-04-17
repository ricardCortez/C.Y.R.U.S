export type VisualPresetId = 'neural' | 'holographic' | 'cyber' | 'organic' | 'monochrome'

export interface PresetPalette {
  node:       [number, number, number]
  connection: [number, number, number]
  pulse:      [number, number, number]
  nucleus:    [number, number, number]
}

export interface PresetConfig {
  id:              VisualPresetId
  name:            string
  palette:         PresetPalette
  rotSpeedMult:    number
  pulseDensity:    number
  glowIntensity:   number
  connectionWidth: number
  gridOverlay:     boolean
}

export const PRESETS: Record<VisualPresetId, PresetConfig> = {
  neural: {
    id: 'neural', name: 'Neural',
    palette: {
      node:       [0.75, 0.90, 1.00],
      connection: [0.30, 0.70, 1.00],
      pulse:      [0.00, 1.00, 0.85],
      nucleus:    [0.50, 0.80, 1.00],
    },
    rotSpeedMult: 1.0, pulseDensity: 1.0,
    glowIntensity: 1.0, connectionWidth: 1.0, gridOverlay: false,
  },
  holographic: {
    id: 'holographic', name: 'Holographic',
    palette: {
      node:       [0.20, 1.00, 0.60],
      connection: [0.00, 0.80, 0.50],
      pulse:      [0.60, 1.00, 0.80],
      nucleus:    [0.10, 0.90, 0.55],
    },
    rotSpeedMult: 0.9, pulseDensity: 0.8,
    glowIntensity: 1.4, connectionWidth: 0.8, gridOverlay: true,
  },
  cyber: {
    id: 'cyber', name: 'Cyber',
    palette: {
      node:       [1.00, 0.55, 0.10],
      connection: [0.90, 0.35, 0.05],
      pulse:      [1.00, 0.80, 0.00],
      nucleus:    [1.00, 0.30, 0.00],
    },
    rotSpeedMult: 1.5, pulseDensity: 1.8,
    glowIntensity: 1.6, connectionWidth: 1.4, gridOverlay: false,
  },
  organic: {
    id: 'organic', name: 'Organic',
    palette: {
      node:       [0.75, 0.55, 1.00],
      connection: [0.55, 0.35, 0.90],
      pulse:      [0.90, 0.70, 1.00],
      nucleus:    [0.65, 0.40, 0.95],
    },
    rotSpeedMult: 0.6, pulseDensity: 0.7,
    glowIntensity: 0.8, connectionWidth: 0.7, gridOverlay: false,
  },
  monochrome: {
    id: 'monochrome', name: 'Mono',
    palette: {
      node:       [1.00, 1.00, 1.00],
      connection: [0.70, 0.70, 0.70],
      pulse:      [1.00, 1.00, 1.00],
      nucleus:    [0.85, 0.85, 0.85],
    },
    rotSpeedMult: 1.0, pulseDensity: 1.0,
    glowIntensity: 1.2, connectionWidth: 1.0, gridOverlay: false,
  },
}

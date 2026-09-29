/**
 * Display metadata for each device type.
 *
 * The server only reports a `type` key (e.g. "tv"). The UI looks up how to
 * present that type here, so presentation stays out of the data. Keep this
 * list in sync with DEVICE_TYPES in server/network.py.
 */
export const DEVICE_TYPES = {
  internet: { label: 'Internet', glyph: 'WAN' },
  router:   { label: 'Router', glyph: 'RTR' },

  computer: { label: 'Desktop PC', glyph: 'PC', color: '#5fd4ff' },
  laptop:   { label: 'Laptop', glyph: 'LAP', color: '#5fd4ff' },
  phone:    { label: 'Phone', glyph: 'PHN', color: '#8c9bff' },
  tablet:   { label: 'Tablet', glyph: 'TAB', color: '#8c9bff' },

  tv:       { label: 'Smart TV', glyph: 'TV', color: '#ff9ecf' },
  media:    { label: 'Streaming box (Apple TV, Roku…)', glyph: 'BOX', color: '#ff9ecf' },
  console:  { label: 'Game console', glyph: 'GAME', color: '#ff9ecf' },
  speaker:  { label: 'Smart speaker', glyph: 'SPK', color: '#ff9ecf' },

  iot:      { label: 'Smart-home (plug, bulb, thermostat…)', glyph: 'IOT', color: '#c792ff' },
  camera:   { label: 'Camera or doorbell', glyph: 'CAM', color: '#c792ff' },
  printer:  { label: 'Printer', glyph: 'PRN', color: '#f5d27a' },
  nas:      { label: 'Network storage (NAS)', glyph: 'NAS', color: '#f5d27a' },
  network:  { label: 'Mesh node, extender or switch', glyph: 'NET' },

  other:    { label: 'Other', glyph: 'DEV' },
  unknown:  { label: 'Unknown', glyph: '?' },
};

/** Legend for the Network map: one swatch per color family (not every type --
 *  computer/laptop share a color, as do the entertainment and home types). */
export const TYPE_LEGEND = [
  { label: 'Computer', color: '#5fd4ff' },
  { label: 'Mobile', color: '#8c9bff' },
  { label: 'Entertainment', color: '#ff9ecf' },
  { label: 'Home & office', color: '#f5d27a' },
  { label: 'Smart-home', color: '#c792ff' },
];

/** How the types are grouped in the "Type" dropdown (router/internet aren't choosable). */
export const TYPE_GROUPS = [
  ['Computers & phones', ['computer', 'laptop', 'phone', 'tablet']],
  ['Entertainment', ['tv', 'media', 'console', 'speaker']],
  ['Home & office', ['iot', 'camera', 'printer', 'nas']],
  ['Network', ['network']],
  ['Other', ['other', 'unknown']],
];

const UNKNOWN_TYPE = { label: 'Unknown', glyph: '?' };

export function getDeviceType(type) {
  return DEVICE_TYPES[type] ?? UNKNOWN_TYPE;
}

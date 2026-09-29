/**
 * Gives every node without a `position` a place on the map.
 *
 * Simulated data comes with hand-picked positions; live data doesn't. The
 * layout is a simple tree: Internet on top, the router below it, and all
 * other devices in rows underneath, in the order the data source lists them.
 *
 * Rows alternate between 5 and 4 slots, and the 4-slot rows sit in the gaps
 * of the row above, so links to lower rows don't run through other devices.
 * Positions are fractions of the map's base size (y may exceed 1 when there
 * are many rows; the map grows to fit).
 */
const WIDE_ROW = 5;
const FIRST_ROW_Y = 0.72;
const ROW_GAP = 0.34;

const slotsInRow = (row) => (row % 2 === 0 ? WIDE_ROW : WIDE_ROW - 1);

// How far each row bows upward at its center, before settling back down at the
// edges -- turns a flat grid row into a gentle arc, like the rest of the app's
// curved, orbiting shapes rather than a straight ruled line.
const ARC_DEPTH = 0.05;

/** Position for the `count` devices in `row`, centred in that row's slots and
 *  arranged along a shallow arc instead of a flat line. */
function rowPositions(row, count) {
  const start = Math.floor((slotsInRow(row) - count) / 2);
  const offset = row % 2 === 0 ? 1 : 1.5; // odd rows shift half a slot into the gaps
  return Array.from({ length: count }, (_, i) => {
    const x = (start + i + offset) / (WIDE_ROW + 1);
    const bow = Math.cos((x - 0.5) * Math.PI) * ARC_DEPTH; // 1 at center, 0 at the edges
    return { x, y: FIRST_ROW_Y + row * ROW_GAP - bow };
  });
}

export function layoutNodes(nodes) {
  if (nodes.every((n) => n.position)) return nodes;

  // Work out every device's position up front, row by row.
  const devices = nodes.filter((n) => n.type !== 'internet' && n.type !== 'router');
  const positions = new Map();
  let placed = 0;
  for (let row = 0; placed < devices.length; row += 1) {
    const batch = devices.slice(placed, placed + slotsInRow(row));
    rowPositions(row, batch.length).forEach((pos, i) => positions.set(batch[i].id, pos));
    placed += batch.length;
  }

  return nodes.map((node) => {
    if (node.position) return node;
    if (node.type === 'internet') return { ...node, position: { x: 0.5, y: 0.13 } };
    if (node.type === 'router') return { ...node, position: { x: 0.5, y: 0.42 } };
    return { ...node, position: positions.get(node.id) };
  });
}

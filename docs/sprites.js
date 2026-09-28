// Piezas pixel art 16x16 dibujadas en codigo: sin assets externos ni licencias de terceros.
// O = contorno, F = relleno, H = brillo, S = sombra, . = transparente
const SPRITES = {
  p: [
    "................",
    "................",
    "................",
    "......OOOO......",
    ".....OHFFSO.....",
    ".....OHFFSO.....",
    ".....OFFFSO.....",
    "......OFSO......",
    ".....OFFFSO.....",
    "......OFSO......",
    "......OFSO......",
    ".....OFFFSO.....",
    "....OFFFFFSO....",
    "...OFFFFFFFSO...",
    "...OOOOOOOOOO...",
    "................",
  ],
  n: [
    "................",
    "................",
    "......OO.O......",
    ".....OFFOFO.....",
    "....OFHFFFFO....",
    "...OFHFOFFFSO...",
    "..OFHFFFFFFFSO..",
    "..OFFFFOOFFFSO..",
    "...OOOO.OFFFSO..",
    ".......OFFFFSO..",
    "......OFFFFFSO..",
    ".....OFFFFFFSO..",
    "....OFFFFFFFSO..",
    "...OFFFFFFFFFSO.",
    "...OOOOOOOOOOOO.",
    "................",
  ],
  b: [
    "................",
    ".......OO.......",
    "......OHFO......",
    "......OFSO......",
    ".....OHFFSO.....",
    "....OHFFOFSO....",
    "....OHFOFFSO....",
    "....OFFFFFSO....",
    ".....OFFFSO.....",
    "......OFSO......",
    ".....OOOOOO.....",
    ".....OFFFSO.....",
    "....OFFFFFSO....",
    "...OFFFFFFFSO...",
    "...OOOOOOOOOO...",
    "................",
  ],
  r: [
    "................",
    "................",
    "...OO..OO..OO...",
    "...OHOOFFOOSO...",
    "...OHFFFFFFSO...",
    "...OOOOOOOOOO...",
    "....OHFFFFSO....",
    "....OHFFFFSO....",
    "....OHFFFFSO....",
    "....OHFFFFSO....",
    "....OHFFFFSO....",
    "...OOOOOOOOOO...",
    "...OHFFFFFFSO...",
    "..OFFFFFFFFFSO..",
    "..OOOOOOOOOOOO..",
    "................",
  ],
  q: [
    "................",
    "..O....OO....O..",
    "..OO..OHFO..OO..",
    "..OHOOHFFSOOSO..",
    "..OHFHFFFFFFSO..",
    "...OHFFFFFFSO...",
    "...OOOOOOOOOO...",
    "....OHFFFFSO....",
    "....OHFFFFSO....",
    ".....OHFFSO.....",
    "....OHFFFFSO....",
    "...OOOOOOOOOO...",
    "...OHFFFFFFSO...",
    "..OFFFFFFFFFSO..",
    "..OOOOOOOOOOOO..",
    "................",
  ],
  k: [
    "......OOOO......",
    "......OHSO......",
    "....OOOHSOOO....",
    "....OHHFFSSO....",
    "....OOOHSOOO....",
    "...OOOOOOOOOO...",
    "..OHFFFFFFFFSO..",
    "..OHFFFFFFFFSO..",
    "...OHFFFFFFSO...",
    "....OHFFFFSO....",
    "....OOOOOOOO....",
    "...OHFFFFFFSO...",
    "...OHFFFFFFSO...",
    "..OFFFFFFFFFSO..",
    "..OOOOOOOOOOOO..",
    "................",
  ],
};

const PALETTES = {
  w: { O: "#1b1424", F: "#f2ead8", H: "#ffffff", S: "#b9ac93" },
  b: { O: "#07050b", F: "#3d3552", H: "#6f6694", S: "#231e31" },
};

const _spriteCache = {};

// Devuelve un canvas 16x16 con la pieza (letra FEN: mayuscula = blancas).
function pieceSprite(fenChar) {
  if (_spriteCache[fenChar]) return _spriteCache[fenChar];
  const side = fenChar === fenChar.toUpperCase() ? "w" : "b";
  const rows = SPRITES[fenChar.toLowerCase()];
  const pal = PALETTES[side];
  const c = document.createElement("canvas");
  c.width = 16;
  c.height = 16;
  const g = c.getContext("2d");
  rows.forEach((row, y) => {
    [...row].forEach((ch, x) => {
      if (ch === ".") return;
      g.fillStyle = pal[ch];
      g.fillRect(x, y, 1, 1);
    });
  });
  _spriteCache[fenChar] = c;
  return c;
}

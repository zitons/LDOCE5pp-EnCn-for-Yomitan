// Compare two PNG screenshots pixel by pixel and report where they differ.
//   node pngdiff.mjs <a.png> <b.png>
// Decodes both with createImageBitmap + OffscreenCanvas (no npm dependency),
// then reports: identical or not, the changed-pixel count, and the bounding box.
import fs from 'node:fs';

const [aPath, bPath] = [process.argv[2], process.argv[3]];
if (!aPath || !bPath) {
    console.error('usage: node pngdiff.mjs <a.png> <b.png>');
    process.exit(2);
}

async function load(p) {
    const buf = fs.readFileSync(p);
    const bmp = await createImageBitmap(new Blob([buf]));
    const c = new OffscreenCanvas(bmp.width, bmp.height);
    const ctx = c.getContext('2d');
    ctx.drawImage(bmp, 0, 0);
    return {data: ctx.getImageData(0, 0, bmp.width, bmp.height), w: bmp.width, h: bmp.height};
}

const A = await load(aPath);
const B = await load(bPath);
console.log(`A: ${A.w}x${A.h}`);
console.log(`B: ${B.w}x${B.h}`);

if (A.w !== B.w || A.h !== B.h) {
    console.log(`SIZE DIFFERS -- not directly comparable`);
    process.exit(0);
}

const {data: da} = A, {data: db} = B;
let changed = 0, minX = 1e9, minY = 1e9, maxX = -1, maxY = -1;
const bands = new Map();
const BAND = 40;
for (let y = 0; y < A.h; y++) {
    for (let x = 0; x < A.w; x++) {
        const i = (y * A.w + x) * 4;
        if (da[i] !== db[i] || da[i+1] !== db[i+1] || da[i+2] !== db[i+2]) {
            changed++;
            if (x < minX) minX = x;
            if (x > maxX) maxX = x;
            if (y < minY) minY = y;
            if (y > maxY) maxY = y;
            const b = Math.floor(y / BAND);
            bands.set(b, (bands.get(b) || 0) + 1);
        }
    }
}

const total = A.w * A.h;
console.log();
if (changed === 0) {
    console.log('PIXEL DIFF: NONE -- the two renders are pixel-identical');
} else {
    console.log(`PIXEL DIFF: ${changed.toLocaleString()} / ${total.toLocaleString()} ` +
                `(${(changed*100/total).toFixed(4)}%)`);
    console.log(`bbox: x ${minX}..${maxX}, y ${minY}..${maxY}`);
    console.log('changed pixels per 40px band:');
    for (const b of [...bands.keys()].sort((p, q) => p - q)) {
        console.log(`   y ${String(b*BAND).padStart(5)}-${String(b*BAND+BAND-1).padEnd(5)}  ` +
                    `${String(bands.get(b)).padStart(7)}`);
    }
}

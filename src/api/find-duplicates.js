const fs = require('fs');

const data = JSON.parse(fs.readFileSync('./response.json', 'utf-8'));

const seen_duplicates = new Map();

data.forEach((entry, index) => {
  const distance = entry.cosineDistance;

  if (seen_duplicates.has(distance)) {
    const existing = seen_duplicates.get(distance);
    existing.push({ index, url: entry.url, cameraId: entry.metadata?.cameraId });
  } else {
    seen_duplicates.set(distance, [{ index, url: entry.url, cameraId: entry.metadata?.cameraId }]);
  }
});

console.log(`Total entries: ${data.length}`);
const dups = []
seen_duplicates.forEach((dup, i) => {
  console.log(`\n${i + 1}. cosineDistance: ${dup.distance}`);
  const currDups = []
  console.log('   CurrLen:' + dup.length);
  if (dup.length < 2) {
    return;
  }
  dup.forEach(e => {
    currDups.push({ index: e.index, cameraId: e.cameraId, cameraName: data[e.index]?.metadata?.cameraName, source: data[e.index]?.metadata?.source });
    console.log(`   - Index: ${e.index}, CameraId: ${e.cameraId}, cameraName: ${data[e.index]?.metadata?.cameraName}, source: ${data[e.index]?.metadata?.source}  `);
  });
  dups.push({ cosineDistance: dup.distance, duplicates: currDups });
});

fs.writeFileSync('./duplicates.json', JSON.stringify(dups, null, 2));
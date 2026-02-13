#!/usr/bin/env node
/**
 * PocketBase에서 그룹 사진 다운로드
 *
 * Usage:
 *   node download-photos.js <group_id> [--limit=50]
 *
 * Examples:
 *   node download-photos.js 2pg9uk43qkqo688
 *   node download-photos.js 2pg9uk43qkqo688 --limit=10
 */

import { fetchPhotosByGroup, downloadImage } from '../../../src/api/pocketbase.js';
import { mkdirSync, existsSync, readdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = join(__dirname, '../../..');

// Parse arguments
const args = process.argv.slice(2);
const groupId = args.find(a => !a.startsWith('--'));
const limitArg = args.find(a => a.startsWith('--limit='));
const limit = limitArg ? parseInt(limitArg.split('=')[1]) : 50;

if (!groupId) {
  console.error('Usage: node download-photos.js <group_id> [--limit=50]');
  console.error('');
  console.error('Examples:');
  console.error('  node download-photos.js 2pg9uk43qkqo688');
  console.error('  node download-photos.js 2pg9uk43qkqo688 --limit=10');
  process.exit(1);
}

const tempDir = join(projectRoot, 'temp');

// Ensure temp directory exists
if (!existsSync(tempDir)) {
  mkdirSync(tempDir, { recursive: true });
}

console.log(`📥 그룹 ${groupId}에서 사진 다운로드 시작...`);
console.log(`   제한: ${limit}개`);
console.log('');

try {
  const photos = await fetchPhotosByGroup(groupId, { limit });

  if (photos.length === 0) {
    console.log('⚠️  사진이 없습니다.');
    process.exit(0);
  }

  console.log(`📷 ${photos.length}개 사진 발견`);
  console.log('');

  const downloadedFiles = [];

  for (let i = 0; i < photos.length; i++) {
    const photo = photos[i];
    const progress = `[${i + 1}/${photos.length}]`;

    try {
      await downloadImage(photo, tempDir);
      const filename = `${photo.id}.jpg`;
      downloadedFiles.push(filename);
      console.log(`  ✓ ${progress} ${filename}`);
    } catch (err) {
      console.error(`  ✗ ${progress} ${photo.id} 다운로드 실패: ${err.message}`);
    }
  }

  console.log('');
  console.log(`✅ 완료: ${downloadedFiles.length}/${photos.length}개 다운로드됨`);
  console.log(`📁 경로: ${tempDir}`);
  console.log('');

  // Output JSON for programmatic use
  const result = {
    group_id: groupId,
    count: downloadedFiles.length,
    temp_dir: tempDir,
    files: downloadedFiles
  };

  console.log('📋 결과 JSON:');
  console.log(JSON.stringify(result, null, 2));

} catch (err) {
  console.error(`❌ 오류: ${err.message}`);
  process.exit(1);
}

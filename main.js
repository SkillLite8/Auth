const { createClient } = require('bedrock-protocol');
const fs = require('fs').promises;
const path = require('path');
const crypto = require('crypto');
const readline = require('readline');

// ==============================
//  КОНФИГУРАЦИЯ
// ==============================
const CONFIG = {
  version: '1.20.30',           // Базовая версия протокола
  outputDir: './resource_packs',
  logFile: 'rp_dumper.log',
};

const c = {
  reset: '\x1b[0m', bright: '\x1b[1m', dim: '\x1b[2m',
  green: '\x1b[32m', yellow: '\x1b[33m', red: '\x1b[31m',
  cyan: '\x1b[36m', magenta: '\x1b[35m', gray: '\x1b[90m',
};

function drawProgressBar(percentage, width = 30) {
  const filled = Math.round((percentage / 100) * width);
  const empty = width - filled;
  return `[${'█'.repeat(filled)}${'░'.repeat(empty)}] ${percentage.toFixed(1)}%`;
}

class ResourcePackDumper {
  constructor(host, port) {
    this.host = host;
    this.port = port;
    this.client = null;
    this.downloadingPacks = new Map();
    this.logStream = null;
  }

  async init() {
    await fs.mkdir(CONFIG.outputDir, { recursive: true });
    this.logStream = await fs.open(path.join(CONFIG.outputDir, CONFIG.logFile), 'a');
    this.log('🛸 Запуск Resource Pack Dumper v4.4 (Стабильная сборка)', c.bright + c.magenta);
    this.log(`🎯 Сервер: ${this.host}:${this.port}`);
  }

  log(msg, color = c.reset) {
    const timestamp = new Date().toISOString().replace('T', ' ').slice(0, 19);
    const line = `[${timestamp}] ${msg.replace(/\x1b\[[0-9;]*m/g, '')}`;
    console.log(`${c.dim}[${timestamp}]${c.reset} ${color}${msg}${c.reset}`);
    if (this.logStream) this.logStream.write(line + '\n');
  }

  createClient() {
    return createClient({
      host: this.host,
      port: this.port,
      version: CONFIG.version,
      username: 'PackGrabber',
      auth: 'microsoft',
      offline: false,
      encryption: true,
      compression: true,
      raknetBackend: 'js', // Чистый JS-движок для работы внутри скомпилированного .exe
      clientData: {
        DeviceOS: 7, 
        DeviceModel: 'System Product Name (ASUS)',
        LanguageCode: 'ru_RU',
        GameVersion: CONFIG.version,
        DefaultInputMode: 1,
        CurrentInputMode: 1,
        UIProfile: 0,
        ServerAddress: `${this.host}:${this.port}`,
        DeviceSessionId: crypto.randomUUID(),
        PlatformUserId: crypto.randomUUID(),
        DeviceId: crypto.randomUUID(),
        ClientId: crypto.randomUUID(),
        SkinId: 'Geometry_CustomSkin',
        TrustedSkin: true,
        CompatibleWithClientSideChunkGeneration: true
      }
    });
  }

  async start() {
    await this.init();
    try {
      this.client = this.createClient();
    } catch (err) {
      this.log(`❌ Не удалось инициализировать клиент: ${err.message}`, c.red);
      this.stop();
      return;
    }

    this.client.on('connect', () => {
      this.log('🤝 Сетевое рукопожатие RakNet успешно!', c.green);
    });

    // ЭТАП 1: Получение информации о ресурс-паках
    this.client.on('resource_packs_info', (packet) => {
      const { resource_packs } = packet;
      if (!resource_packs || resource_packs.length === 0) {
        this.log('ℹ️ Сервер не требует загрузки кастомных ресурс-паков.', c.yellow);
        this.stop();
        return;
      }

      this.log(`📦 Обнаружено ресурс-паков: ${resource_packs.length}`, c.bright + c.cyan);

      const packsToDownload = [];
      resource_packs.forEach((pack) => {
        this.log(`   -> ID: ${pack.id.slice(0, 8)}... | Размер: ${(pack.size / 1024 / 1024).toFixed(2)} МБ`, c.cyan);
        
        this.downloadingPacks.set(pack.id, {
          id: pack.id,
          size: pack.size,
          chunks: [],
          receivedBytes: 0,
        });
        packsToDownload.push({ uuid: pack.id, version: pack.version });
      });

      this.log('📥 Отправляем согласие на скачивание (WANT_TO_DOWNLOAD)...', c.yellow);
      this.client.send('resource_pack_client_response', {
        response_status: 3, 
        resource_pack_ids: packsToDownload,
      });
    });

    // ЭТАП 2: Сборка файлов из чанков данных
    this.client.on('resource_pack_data_chunk', async (packet) => {
      const { pack_id, chunk_index, data } = packet;
      const pack = this.downloadingPacks.get(pack_id);
      if (!pack) return;

      if (!pack.chunks[chunk_index]) {
        pack.chunks[chunk_index] = data;
        pack.receivedBytes += data.length;
      }

      const progress = Math.min((pack.receivedBytes / pack.size) * 100, 100);
      if (Math.floor(progress) % 10 === 0 || progress >= 100) {
        this.log(`⏳ Пак ${pack_id.slice(0, 8)}... ${drawProgressBar(progress)}`, c.gray);
      }

      if (pack.receivedBytes >= pack.size) {
        this.log(`🎉 Пак ${pack_id.slice(0, 8)}... полностью получен. Склеиваем архив...`, c.green);

        const finalBuffer = Buffer.concat(pack.chunks.filter(Boolean));
        const filePath = path.join(CONFIG.outputDir, `${pack_id}.zip`);

        try {
          await fs.writeFile(filePath, finalBuffer);
          this.log(`💾 Сохранён: ${filePath} (${(finalBuffer.length / 1024 / 1024).toFixed(2)} МБ)`, c.bright + c.green);
        } catch (err) {
          this.log(`❌ Ошибка файловой системы: ${err.message}`, c.red);
        }

        this.downloadingPacks.delete(pack_id);

        if (this.downloadingPacks.size === 0) {
          this.log('🏁 Все доступные ресурс-паки успешно выкачаны!', c.bright + c.magenta);
          this.stop();
        }
      }
    });

    // ЭТАП 3: Финальное подтверждение
    this.client.on('resource_pack_stack', () => {
      this.client.send('resource_pack_client_response', {
        response_status: 4, 
        resource_pack_ids: []
      });
      this.log('📦 Финальный статус пакетов ресурсов отправлен.', c.dim);
    });

    this.client.on('close', (reason) => {
      this.log(`🔌 Соединение закрыто: ${reason || 'Процесс завершен'}`, c.yellow);
      this.stop();
    });

    this.client.on('error', (err) => {
      this.log(`⚠️ Ошибка протокола: ${err.message}`, c.red);
    });
  }

  async stop() {
    if (this.client) {
      try { this.client.close(); } catch {}
      this.client = null;
    }
    if (this.logStream) {
      try { await this.logStream.close(); } catch {}
      this.logStream = null;
    }
    process.exit(0);
  }
}

// ==============================
//  CLI ИНТЕРФЕЙС
// ==============================
const rl = readline.createInterface({ input: process.stdin, output: process.stdout, prompt: `${c.cyan}>${c.reset} ` });

console.log(`\n${c.bright}${c.magenta}╔══════════════════════════════════════════════════════╗
║     🛸  NeverTime RESOURCE PACK Dumper v4.4          ║
║         Назначение: Скачивание .zip РП с сервера     ║
╚══════════════════════════════════════════════════════╝${c.reset}\n`);
console.log(`Введите команду ${c.green}packs${c.reset} для начала.`);
rl.prompt();

rl.on('line', (line) => {
  const cmd = line.trim().toLowerCase();
  if (cmd === 'packs') {
    rl.question(`${c.yellow}Enter Server (ip:port): ${c.reset}`, (input) => {
      let [host, portStr] = input.trim().split(':');
      if (!host) {
        console.log('❌ Неверный адрес.');
        rl.prompt();
        return;
      }
      const port = portStr ? parseInt(portStr, 10) : 19132;
      rl.close();
      
      const dumper = new ResourcePackDumper(host, port);
      dumper.start();
    });
  } else if (cmd === 'exit' || cmd === 'quit') {
    process.exit(0);
  } else {
    console.log(`Используй команду: ${c.green}packs${c.reset}`);
    rl.prompt();
  }
});

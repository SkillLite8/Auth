package main

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/sandertv/gophertunnel/minecraft"
	"github.com/sandertv/gophertunnel/minecraft/auth"
	"github.com/sandertv/gophertunnel/minecraft/protocol/login"
	"golang.org/x/oauth2"
)

const (
	outputDir   = "./resource_packs"
	logFile     = "rp_dumper.log"
	// Актуализированная версия для обхода блокировок по версии (например, 1.21.32)
	gameVersion = "1.21.32" 
)

var ansiRegex = regexp.MustCompile(`\x1b\[[0-9;]*m`)

func logMsg(msg string) {
	fmt.Println(msg)
	clean := ansiRegex.ReplaceAllString(msg, "")
	f, err := os.OpenFile(logFile, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err == nil {
		defer f.Close()
		timestamp := time.Now().Format("15:04:05")
		f.WriteString(fmt.Sprintf("[%s] %s\n", timestamp, clean))
	}
}

func splitHostPort(input string) (string, int) {
	parts := strings.Split(input, ":")
	if len(parts) == 1 {
		return parts[0], 19132
	}
	port, _ := strconv.Atoi(parts[1])
	return parts[0], port
}

type Dumper struct {
	host        string
	port        int
	tokenSource oauth2.TokenSource
	conn        *minecraft.Conn
}

func NewDumper(host string, port int, tokenSource oauth2.TokenSource) *Dumper {
	return &Dumper{host: host, port: port, tokenSource: tokenSource}
}

// connectWithRetry выполняет connect с несколькими попытками и экспоненциальной задержкой
func (d *Dumper) connectWithRetry(maxAttempts int, baseDelay time.Duration) error {
	var lastErr error
	for attempt := 1; attempt <= maxAttempts; attempt++ {
		logMsg(fmt.Sprintf("Попытка подключения %d/%d...", attempt, maxAttempts))
		err := d.connect()
		if err == nil {
			return nil
		}
		lastErr = err
		logMsg(fmt.Sprintf("\x1b[1;31m❌ Ошибка подключения (попытка %d): %v\x1b[0m", attempt, err))
		if attempt < maxAttempts {
			delay := baseDelay * time.Duration(1<<(attempt-1)) // 2s, 4s, 8s...
			logMsg(fmt.Sprintf("Ожидание %v перед следующей попыткой...", delay))
			time.Sleep(delay)
		}
	}
	return fmt.Errorf("не удалось подключиться после %d попыток: %w", maxAttempts, lastErr)
}

func (d *Dumper) connect() error {
	// Эмуляция официального клиента Windows 10/11 для обхода Anti-Cheat / Anti-Bot систем
	clientData := login.ClientData{
		DeviceOS:            7, // Windows
		DeviceModel:         "Windows 10",
		DeviceID:            login.DeviceID(uuid.New().String()),
		ClientRandomID:      time.Now().UnixNano(),
		GameVersion:         gameVersion,
		ServerAddress:       fmt.Sprintf("%s:%d", d.host, d.port),
		SkinID:              "Default",
		SkinData:            "",
		SkinImageWidth:      0,
		SkinImageHeight:     0,
		SkinResourcePatch:   "",
		SkinGeometry:        "",
		SkinGeometryVersion: "",
		SkinAnimationData:   "",
		CapeData:            "",
		CapeImageWidth:      0,
		CapeImageHeight:     0,
		TrustedSkin:         true,
		LanguageCode:        "ru_RU",
		CurrentInputMode:    1, // Keyboard & Mouse
		DefaultInputMode:    1,
	}

	dialer := minecraft.Dialer{
		ClientData:  clientData,
		TokenSource: d.tokenSource,
	}

	addr := fmt.Sprintf("%s:%d", d.host, d.port)
	// Устанавливаем таймаут на подключение, чтобы скрипт не зависал бесконечно
	conn, err := dialer.Dial("raknet", addr)
	if err != nil {
		return err
	}
	d.conn = conn
	return nil
}

func (d *Dumper) Run() error {
	if err := d.connectWithRetry(3, 2*time.Second); err != nil {
		return err
	}
	defer d.conn.Close()

	logMsg("\x1b[1;32m✅ Подключено к серверу! Ожидание дешифровки пакетов и получения списка РП...\x1b[0m")
	
	// Небольшая пауза, чтобы прокси-сервер успел прислать ResourcePacksInfo пакет
	time.Sleep(1 * time.Second)

	packs := d.conn.ResourcePacks()
	if len(packs) == 0 {
		logMsg("\x1b[1;33m⚠️ Сервер не передал ресурс-паки. Возможные причины:\x1b[0m")
		logMsg("   1. Сервер использует защиту Anti-Dump (паки скрыты или вырезаны на этапе логина).")
		logMsg("   2. Версия " + gameVersion + " не поддерживается сервером (попробуйте изменить константу gameVersion).")
		return nil
	}

	logMsg(fmt.Sprintf("\x1b[1;36m📦 Найдено %d ресурс-паков\x1b[0m", len(packs)))

	for i, pack := range packs {
		logMsg(fmt.Sprintf("\x1b[1;34m[%d/%d] Скачивание пака: %s\x1b[0m", i+1, len(packs), pack.UUID().String()))
		if err := d.downloadPack(pack); err != nil {
			logMsg(fmt.Sprintf("\x1b[1;31m❌ Ошибка при скачивании пака %s: %v\x1b[0m", pack.UUID().String(), err))
		}
	}

	logMsg("\x1b[1;35m🏁 Процесс завершен. Проверьте папку " + outputDir + "\x1b[0m")
	return nil
}

func (d *Dumper) downloadPack(pack interface{}) error {
	type Pack interface {
		UUID() uuid.UUID
		Reader() io.ReadCloser
	}
	p, ok := pack.(Pack)
	if !ok {
		return fmt.Errorf("неверный тип ресурс-пака в библиотеке gophertunnel")
	}

	rc := p.Reader()
	if rc == nil {
		return fmt.Errorf("сервер заблокировал чтение (Reader вернул nil). Возможно пак зашифрован")
	}
	defer rc.Close()

	_ = os.MkdirAll(outputDir, os.ModePerm)
	outPath := filepath.Join(outputDir, p.UUID().String()+".zip")
	f, err := os.Create(outPath)
	if err != nil {
		return fmt.Errorf("не удалось создать файл: %w", err)
	}
	defer f.Close()

	// Оптимальный буфер в 1 МБ для быстрой записи больших текстур-паков
	buf := make([]byte, 1024*1024)
	var written int64
	lastMB := int64(-1)

	for {
		n, readErr := rc.Read(buf)
		if n > 0 {
			if _, writeErr := f.Write(buf[:n]); writeErr != nil {
				return fmt.Errorf("ошибка записи на диск: %w", writeErr)
			}
			written += int64(n)
			currentMB := written / (1024 * 1024)
			if currentMB > lastMB {
				logMsg(fmt.Sprintf("   ⏳ Скачано: %d MB", currentMB))
				lastMB = currentMB
			}
		}
		if readErr != nil {
			if readErr == io.EOF {
				break
			}
			return fmt.Errorf("ошибка чтения потока данных: %w", readErr)
		}
	}

	sizeMB := float64(written) / (1024 * 1024)
	if sizeMB == 0 {
		logMsg(fmt.Sprintf("\x1b[1;33m⚠️ Предупреждение: Скачанный файл %s пуст (0 MB). Сервер скормил заглушку.\x1b[0m", p.UUID().String()))
	} else {
		logMsg(fmt.Sprintf("\x1b[1;32m✅ Успешно сохранён: %s (%.2f MB)\x1b[0m", filepath.Base(outPath), sizeMB))
	}
	return nil
}

func main() {
	// Из соображений совместимости с Go 1.20+ rand.Seed удален, так как рантайм Go теперь делает это сам автоматически.
	_ = os.WriteFile(logFile, []byte("--- Dumper Log Start ---\n"), 0644)

	logMsg("\x1b[1;35m╔══════════════════════════════════════════════════════╗\x1b[0m")
	logMsg("\x1b[1;35m║     🛸  NeverTime RP Dumper v9.0  (Go 2026)        ║\x1b[0m")
	logMsg("\x1b[1;35m║          Скачивание ресурс-паков с обходом         ║\x1b[0m")
	logMsg("\x1b[1;35m╚══════════════════════════════════════════════════════╝\x1b[0m")

	reader := bufio.NewReader(os.Stdin)
	fmt.Print("Введите 'packs' для начала работы: ")
	cmd, _ := reader.ReadString('\n')
	if strings.TrimSpace(cmd) != "packs" {
		logMsg("Отмена операции. Выход.")
		return
	}

	fmt.Print("Введите IP:Порт (например, mc.nevertime.su:19132): ")
	input, _ := reader.ReadString('\n')
	host, port := splitHostPort(strings.TrimSpace(input))

	logMsg("\x1b[1;33m⏳ Запрос токена Xbox Live. Пожалуйста, пройдите авторизацию в открывшемся окне браузера...\x1b[0m")
	token, err := auth.RequestLiveToken()
	if err != nil {
		logMsg(fmt.Sprintf("\x1b[1;31m❌ Ошибка авторизации Xbox Live: %v\x1b[0m", err))
		return
	}
	tokenSrc := oauth2.StaticTokenSource(token)
	logMsg("\x1b[1;32m✅ Токен успешно получен.\x1b[0m")

	dumper := NewDumper(host, port, tokenSrc)
	if err := dumper.Run(); err != nil {
		logMsg(fmt.Sprintf("\x1b[1;31m❌ Критический сбой программы: %v\x1b[0m", err))
	}
}

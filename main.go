package main

import (
	"bufio"
	"fmt"
	"io"
	"math/rand"
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
	gameVersion = "1.21.0" // Используем актуальную версию протокола
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

func randDelay(minMs, maxMs int) time.Duration {
	return time.Duration(rand.Intn(maxMs-minMs+1)+minMs) * time.Millisecond
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

func (d *Dumper) Run() error {
	if err := d.connect(); err != nil {
		return err
	}
	defer d.conn.Close()

	logMsg("\x1b[1;32m✅ Подключено к серверу!\x1b[0m")
	time.Sleep(3 * time.Second)

	packs := d.conn.ResourcePacks()
	if len(packs) == 0 {
		logMsg("\x1b[1;33m⚠️ Сервер не предоставил ресурс-паки.\x1b[0m")
		return nil
	}

	logMsg(fmt.Sprintf("\x1b[1;36m📦 Найдено %d ресурс-паков\x1b[0m", len(packs)))

	for i, pack := range packs {
		logMsg(fmt.Sprintf("\x1b[1;34m[%d/%d] Скачивание: %s\x1b[0m", i+1, len(packs), pack.UUID().String()))
		
		_ = os.MkdirAll(outputDir, os.ModePerm)
		outPath := filepath.Join(outputDir, pack.UUID().String()+".zip")
		
		err := d.download(pack.Reader(), outPath)
		if err != nil {
			logMsg(fmt.Sprintf("\x1b[1;31m❌ Ошибка скачивания: %v\x1b[0m", err))
		}
	}

	logMsg("\x1b[1;35m🏁 Все ресурс-паки успешно выкачаны!\x1b[0m")
	return nil
}

func (d *Dumper) connect() error {
	clientData := login.ClientData{
		DeviceOS:            7,
		DeviceModel:         "Windows 10",
		DeviceID:            login.DeviceID(uuid.New().String()),
		ClientRandomID:      time.Now().UnixNano(),
		GameVersion:         gameVersion,
		ServerAddress:       fmt.Sprintf("%s:%d", d.host, d.port),
		SkinID:              "Default",
		TrustedSkin:         true,
		LanguageCode:        "ru_RU",
	}

	dialer := minecraft.Dialer{
		ClientData:  clientData,
		TokenSource: d.tokenSource,
	}

	addr := fmt.Sprintf("%s:%d", d.host, d.port)
	conn, err := dialer.Dial("raknet", addr)
	if err != nil {
		return err
	}
	d.conn = conn
	return nil
}

func (d *Dumper) download(rc io.ReadCloser, outPath string) error {
	defer rc.Close()

	f, err := os.Create(outPath)
	if err != nil {
		return err
	}
	defer f.Close()

	buf := make([]byte, 1024*1024)
	var written int64
	lastPercent := -1

	for {
		n, err := rc.Read(buf)
		if n > 0 {
			_, werr := f.Write(buf[:n])
			if werr != nil {
				return werr
			}
			written += int64(n)
			if written/1024/1024 > int64(lastPercent+1) {
				percent := int(written / 1024 / 1024)
				if percent%5 == 0 {
					logMsg(fmt.Sprintf("\x1b[2m   ⏳ %s\x1b[0m", formatFileSize(written)))
					lastPercent = percent
				}
			}
			time.Sleep(randDelay(5, 20))
		}
		if err != nil {
			if err == io.EOF {
				break
			}
			return err
		}
	}

	logMsg(fmt.Sprintf("\x1b[1;32m✅ Сохранён: %s (%.2f MB)\x1b[0m", filepath.Base(outPath), float64(written)/1024/1024))
	return nil
}

func formatFileSize(bytes int64) string {
	const unit = 1024
	if bytes < unit {
		return fmt.Sprintf("%d B", bytes)
	}
	div, exp := int64(unit), 0
	for n := bytes / unit; n >= unit; n /= unit {
		div *= unit
		exp++
	}
	return fmt.Sprintf("%.1f %cB", float64(bytes)/float64(div), "KMGTPE"[exp])
}

func main() {
	rand.Seed(time.Now().UnixNano())
	_ = os.WriteFile(logFile, []byte("--- Dumper Log Start ---\n"), 0644)

	logMsg("\x1b[1;35m╔══════════════════════════════════════════════════════╗\x1b[0m")
	logMsg("\x1b[1;35m║     🛸  NeverTime RP Dumper v8.0  (Stable)         ║\x1b[0m")
	logMsg("\x1b[1;35m║          Скачивание ресурс-паков с обходом         ║\x1b[0m")
	logMsg("\x1b[1;35m╚══════════════════════════════════════════════════════╝\x1b[0m")

	reader := bufio.NewReader(os.Stdin)
	fmt.Print("Введите 'packs' для начала: ")
	cmd, _ := reader.ReadString('\n')
	if strings.TrimSpace(cmd) != "packs" {
		logMsg("Выход.")
		return // Здесь консоль закроется, так как не ввели packs
	}

	fmt.Print("IP:Порт сервера (например mc.nevertime.su:19132): ")
	input, _ := reader.ReadString('\n')
	host, port := splitHostPort(strings.TrimSpace(input))

	fmt.Print("Использовать Xbox Auth? (y/n): ")
	useXbox, _ := reader.ReadString('\n')
	
	var tokenSrc oauth2.TokenSource
	isAuthError := false

	if strings.TrimSpace(strings.ToLower(useXbox)) == "y" {
		logMsg("\x1b[1;33m⏳ Откройте ссылку в браузере и введите код.\x1b[0m")
		var err error
		tokenSrc, err = auth.RequestLiveToken()
		if err != nil {
			logMsg(fmt.Sprintf("\x1b[1;31m❌ Ошибка получения токена Xbox: %v\x1b[0m", err))
			isAuthError = true
		} else {
			logMsg("\x1b[1;32m✅ Xbox-авторизация выполнена.\x1b[0m")
		}
	} else {
		tokenSrc = nil
	}

	// Если не было критической ошибки авторизации — запускаем дамп
	if !isAuthError {
		dumper := NewDumper(host, port, tokenSrc)
		if err := dumper.Run(); err != nil {
			logMsg(fmt.Sprintf("\x1b[1;31m❌ Критическая ошибка: %v\x1b[0m", err))
		}
	}

	// ОЖИДАНИЕ ПЕРЕД ЗАКРЫТИЕМ: чтобы можно было прочитать ошибку
	fmt.Print("\nНажмите Enter, чтобы закрыть программу...")
	reader.ReadString('\n')
}

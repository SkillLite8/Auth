package main

import (
	"bufio"
	"context"
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
	// Устанавливаем актуальную внутреннюю версию протокола сервера 26.20
	gameVersion = "1.26.20" 
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

func (d *Dumper) Run() error {
	// Инициализируем симуляцию легитимного клиента Windows 11 / Xbox
	clientData := login.ClientData{
		DeviceOS:          7, // Windows 10/11
		DeviceModel:       "Custom PC (Ryzen 7, RTX 4060)",
		DeviceID:          login.DeviceID(uuid.New().String()),
		ClientRandomID:    time.Now().UnixNano(),
		GameVersion:       gameVersion,
		ServerAddress:     fmt.Sprintf("%s:%d", d.host, d.port),
		SkinID:            "GeometryCustomSkin",
		TrustedSkin:       true,
		LanguageCode:      "ru_RU",
		CurrentInputMode:  1, // Клавиатура + Мышь
		DefaultInputMode:  1,
		PlatformOnlineID:  uuid.New().String(),
		PlatformOfflineID: uuid.New().String(),
		PremiumSkin:       true,
		PersonaSkin:       false,
	}

	dialer := minecraft.Dialer{
		ClientData:  clientData,
		TokenSource: d.tokenSource,
	}

	addr := fmt.Sprintf("%s:%d", d.host, d.port)
	logMsg(fmt.Sprintf("🚀 Запуск симуляции игрока. Подключение к %s...", addr))

	// Увеличиваем таймаут ожидания пакетов до 45 секунд под прокси/VPN соединения
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()

	conn, err := dialer.DialContext(ctx, "raknet", addr)
	if err != nil {
		return fmt.Errorf("ошибка авторизации на сервере: %w", err)
	}
	d.conn = conn
	defer d.conn.Close()

	logMsg("\x1b[1;32m✅ Успешное вхождение в сеть сервера. Эмуляция завершена.\x1b[0m")
	
	// Ожидание завершения внутреннего хэндшейка со стороны ядра
	time.Sleep(2 * time.Second)

	packs := d.conn.ResourcePacks()
	if len(packs) == 0 {
		logMsg("\x1b[1;33m⚠️ Сервер успешно принял сессию, но не передал массив ресурс-паков.\x1b[0m")
		return nil
	}

	logMsg(fmt.Sprintf("\x1b[1;36m📦 Обнаружено доступных ресурс-паков: %d\x1b[0m", len(packs)))

	for i, pack := range packs {
		logMsg(fmt.Sprintf("   📥 [%d/%d] Чтение потока: %s", i+1, len(packs), pack.UUID().String()))
		if err := d.downloadPack(pack); err != nil {
			logMsg(fmt.Sprintf("\x1b[1;31m      ❌ Ошибка: %v\x1b[0m", err))
		}
	}

	return nil
}

func (d *Dumper) downloadPack(pack interface{}) error {
	type Pack interface {
		UUID() uuid.UUID
		Reader() io.ReadCloser
	}
	p, ok := pack.(Pack)
	if !ok {
		return fmt.Errorf("неверный тип структуры данных пакета")
	}

	rc := p.Reader()
	if rc == nil {
		return fmt.Errorf("пустой поток данных (заблокировано ядром сервера)")
	}
	defer rc.Close()

	_ = os.MkdirAll(outputDir, os.ModePerm)
	outPath := filepath.Join(outputDir, p.UUID().String()+".zip")
	f, err := os.Create(outPath)
	if err != nil {
		return fmt.Errorf("ошибка создания локального файла: %w", err)
	}
	defer f.Close()

	buf := make([]byte, 1024*1024)
	var written int64

	for {
		n, readErr := rc.Read(buf)
		if n > 0 {
			if _, writeErr := f.Write(buf[:n]); writeErr != nil {
				return fmt.Errorf("ошибка записи: %w", writeErr)
			}
			written += int64(n)
		}
		if readErr != nil {
			if readErr == io.EOF {
				break
			}
			return fmt.Errorf("ошибка чтения потока: %w", readErr)
		}
	}

	sizeMB := float64(written) / (1024 * 1024)
	logMsg(fmt.Sprintf("\x1b[1;32m      ✅ Файл успешно выгружен (Размер: %.2f MB)\x1b[0m", sizeMB))
	return nil
}

func main() {
	_ = os.WriteFile(logFile, []byte("--- Dumper Log Start ---\n"), 0644)

	logMsg("\x1b[1;35m╔══════════════════════════════════════════════════════╗\x1b[0m")
	logMsg("\x1b[1;35m║     🛸  NeverTime Client Emulator v11.1 (Go)       ║\x1b[0m")
	logMsg("\x1b[1;35m╚══════════════════════════════════════════════════════╝\x1b[0m")

	reader := bufio.NewReader(os.Stdin)
	fmt.Print("Введите 'packs' для старта: ")
	cmd, _ := reader.ReadString('\n')
	if strings.TrimSpace(cmd) != "packs" {
		return
	}

	fmt.Print("IP:Порт сервера: ")
	input, _ := reader.ReadString('\n')
	host, port := splitHostPort(strings.TrimSpace(input))

	logMsg("\x1b[1;33m⏳ Запуск процесса обмена токенов Xbox Live...\x1b[0m")
	token, err := auth.RequestLiveToken()
	if err != nil {
		logMsg(fmt.Sprintf("❌ Критическая ошибка авторизации Live: %v", err))
		return
	}
	tokenSrc := oauth2.StaticTokenSource(token)

	dumper := NewDumper(host, port, tokenSrc)
	if err := dumper.Run(); err != nil {
		logMsg(fmt.Sprintf("\x1b[1;31m❌ Ошибка выполнения: %v\x1b[0m", err))
	}
}

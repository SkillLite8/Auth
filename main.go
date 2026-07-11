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

var ansiRegex = regexp.MustCompile(`\x1b\[[0-9;]*m`)
var logFile string
var baseDir string
var outputDir = "resource_packs"

func initPaths() {
	exePath, err := os.Executable()
	if err != nil {
		baseDir = "."
	} else {
		baseDir = filepath.Dir(exePath)
	}
	logFile = filepath.Join(baseDir, "rp_dumper.log")
}

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
}

func NewDumper(host string, port int, tokenSource oauth2.TokenSource) *Dumper {
	return &Dumper{host: host, port: port, tokenSource: tokenSource}
}

func (d *Dumper) connectWithRetry(version string, maxAttempts int) (*minecraft.Conn, error) {
	var lastErr error
	for attempt := 1; attempt <= maxAttempts; attempt++ {
		logMsg(fmt.Sprintf("Попытка подключения %d/%d (версия %s)...", attempt, maxAttempts, version))
		conn, err := d.tryConnect(version)
		if err == nil {
			return conn, nil
		}
		lastErr = err
		logMsg(fmt.Sprintf("\x1b[1;31m❌ Ошибка: %v\x1b[0m", err))
		if attempt < maxAttempts {
			delay := time.Duration(2<<(attempt-1)) * time.Second
			logMsg(fmt.Sprintf("Ожидание %v...", delay))
			time.Sleep(delay)
		}
	}
	return nil, fmt.Errorf("не удалось подключиться после %d попыток: %w", maxAttempts, lastErr)
}

func (d *Dumper) tryConnect(ver string) (*minecraft.Conn, error) {
	addr := fmt.Sprintf("%s:%d", d.host, d.port)
	deviceID := login.DeviceID(uuid.New().String())
	platformOnlineID := uuid.New().String()
	platformOfflineID := uuid.New().String()

	clientData := login.ClientData{
		DeviceOS:           7,
		DeviceModel:        "Windows 10",
		DeviceID:           deviceID,
		ClientRandomID:     time.Now().UnixNano(),
		GameVersion:        ver,
		ServerAddress:      addr,
		SkinID:             "",
		SkinData:           "",
		SkinImageWidth:     64,
		SkinImageHeight:    32,
		SkinResourcePatch:  "",
		SkinGeometry:       "",
		SkinGeometryVersion: "",
		SkinAnimationData:  "",
		CapeID:             "",
		CapeData:           "",
		CapeImageWidth:     64,
		CapeImageHeight:    32,
		CapeOnClassicSkin:  false,
		PersonaSkin:        true,
		PremiumSkin:        true,
		TrustedSkin:        true,
		LanguageCode:       "ru_RU",
		PlatformOnlineID:   platformOnlineID,
		PlatformOfflineID:  platformOfflineID,
		CurrentInputMode:   1,
		DefaultInputMode:   1,
	}

	dialer := minecraft.Dialer{
		ClientData:  clientData,
		TokenSource: d.tokenSource,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	conn, err := dialer.DialContext(ctx, "raknet", addr)
	if err != nil {
		return nil, err
	}
	return conn, nil
}

func (d *Dumper) Run(version string) error {
	conn, err := d.connectWithRetry(version, 5)
	if err != nil {
		return err
	}
	defer conn.Close()

	logMsg("\x1b[1;32m✅ Соединение установлено! Запрашиваем ресурс-паки...\x1b[0m")

	// Даём серверу время отправить ResourcePacksInfo
	time.Sleep(5 * time.Second)

	packs := conn.ResourcePacks()
	if len(packs) == 0 {
		logMsg("\x1b[1;33m⚠️ Сервер не прислал паки (возможно, требует дополнительной авторизации).\x1b[0m")
		return nil
	}

	outputPacksDir := filepath.Join(baseDir, outputDir)
	logMsg(fmt.Sprintf("\x1b[1;36m📦 Найдено %d пак(ов). Сохраняем в %s\x1b[0m", len(packs), outputPacksDir))

	for i, pack := range packs {
		logMsg(fmt.Sprintf("   📥 [%d/%d] Загрузка %s", i+1, len(packs), pack.UUID().String()))
		if err := d.downloadPack(pack, outputPacksDir); err != nil {
			logMsg(fmt.Sprintf("\x1b[1;31m      ❌ Ошибка: %v\x1b[0m", err))
		}
	}

	logMsg("\x1b[1;35m🏁 Все ресурс-паки успешно выкачаны!\x1b[0m")
	return nil
}

func (d *Dumper) downloadPack(pack interface{}, targetDir string) error {
	type Pack interface {
		UUID() uuid.UUID
		Reader() io.ReadCloser
	}
	p, ok := pack.(Pack)
	if !ok {
		return fmt.Errorf("неверный тип пака")
	}
	rc := p.Reader()
	if rc == nil {
		return fmt.Errorf("нет данных для чтения")
	}
	defer rc.Close()

	_ = os.MkdirAll(targetDir, os.ModePerm)
	outPath := filepath.Join(targetDir, p.UUID().String()+".zip")
	f, err := os.Create(outPath)
	if err != nil {
		return err
	}
	defer f.Close()

	written, _ := io.Copy(f, rc)
	sizeMB := float64(written) / (1024 * 1024)
	logMsg(fmt.Sprintf("\x1b[1;32m      ✅ Сохранён: %s (%.2f MB)\x1b[0m", filepath.Base(outPath), sizeMB))
	return nil
}

func main() {
	// Защита от мгновенного закрытия окна при панике и штатном завершении
	defer func() {
		if r := recover(); r != nil {
			fmt.Printf("\n[PANIC] %v\n", r)
		}
		fmt.Println("\nНажмите Enter для выхода...")
		bufio.NewReader(os.Stdin).ReadBytes('\n')
	}()

	initPaths()
	_ = os.WriteFile(logFile, []byte("--- Dumper Log Start ---\n"), 0644)

	logMsg("\x1b[1;35m╔══════════════════════════════════════════════════════╗\x1b[0m")
	logMsg("\x1b[1;35m║  🛸 NeverTime RP Dumper v14.0 (Smart Ping + Bruteforce)  ║\x1b[0m")
	logMsg("\x1b[1;35m╚══════════════════════════════════════════════════════╝\x1b[0m")

	reader := bufio.NewReader(os.Stdin)
	fmt.Print("Введите 'packs' для запуска: ")
	cmd, _ := reader.ReadString('\n')
	if strings.TrimSpace(cmd) != "packs" {
		return
	}

	fmt.Print("IP:Порт сервера (например mc.nevertime.su:19132): ")
	input, _ := reader.ReadString('\n')
	host, port := splitHostPort(strings.TrimSpace(input))

	// Определяем версию сервера
	logMsg("\x1b[1;33m⏳ Пинг сервера...\x1b[0m")
	version := ""
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	pong, err := minecraft.PingContext(ctx, fmt.Sprintf("%s:%d", host, port))
	if err == nil {
		version = pong.Version
		logMsg(fmt.Sprintf("✅ Версия сервера: %s", version))
	} else {
		logMsg(fmt.Sprintf("❌ Пинг не удался: %v", err))
		logMsg("Попробуем подобрать версию автоматически...")
		versionsToTry := []string{
			"1.21.30", "1.21.20", "1.21.0", "1.20.80", "1.20.50", "1.20.30",
			"1.20.10", "1.20.0", "1.19.80", "1.19.70",
		}
		for _, v := range versionsToTry {
			logMsg(fmt.Sprintf("Пробуем версию %s...", v))
			conn, err := NewDumper(host, port, nil).tryConnect(v)
			if err == nil {
				logMsg(fmt.Sprintf("\x1b[1;32m🔥 Подошла версия %s\x1b[0m", v))
				version = v
				conn.Close()
				break
			}
		}
	}

	if version == "" {
		logMsg("\x1b[1;31m❌ Не удалось определить рабочую версию.\x1b[0m")
		return
	}

	// Авторизация Xbox Live
	logMsg("\x1b[1;33m⏳ Авторизация Xbox Live...\x1b[0m")
	token, err := auth.RequestLiveToken()
	if err != nil {
		logMsg(fmt.Sprintf("❌ Ошибка Xbox: %v", err))
		return
	}
	tokenSrc := oauth2.StaticTokenSource(token)
	logMsg("\x1b[1;32m✅ Xbox-авторизация пройдена.\x1b[0m")

	dumper := NewDumper(host, port, tokenSrc)
	if err := dumper.Run(version); err != nil {
		logMsg(fmt.Sprintf("\x1b[1;31m❌ Критическая ошибка: %v\x1b[0m", err))
	}
}

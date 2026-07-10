package main

import (
	"bufio"
	"context"
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
	"github.com/sandertv/gophertunnel/minecraft/protocol"
	"github.com/sandertv/gophertunnel/minecraft/protocol/login"
	"github.com/sandertv/gophertunnel/minecraft/protocol/packet"
	"golang.org/x/oauth2"
)

// ===========================
//  КОНФИГУРАЦИЯ
// ===========================
const (
	outputDir       = "./resource_packs"
	logFile         = "rp_dumper.log"
	protocolVersion = 594 // 1.20.30 / 1.21.0 – уточните для вашего сервера
	gameVersion     = "1.20.30"
)

var ansiRegex = regexp.MustCompile(`\x1b\[[0-9;]*m`)

// ===========================
//  ЛОГГЕР
// ===========================
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

// ===========================
//  УТИЛИТЫ
// ===========================
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

// ===========================
//  ОСНОВНОЙ ТИП – ДАМПЕР
// ===========================
type Dumper struct {
	host        string
	port        int
	tokenSource oauth2.TokenSource
	conn        *minecraft.Conn
	done        chan bool
}

func NewDumper(host string, port int, tokenSource oauth2.TokenSource) *Dumper {
	return &Dumper{
		host:        host,
		port:        port,
		tokenSource: tokenSource,
		done:        make(chan bool),
	}
}

func (d *Dumper) Run() error {
	if err := d.connect(); err != nil {
		return err
	}
	defer d.conn.Close()

	logMsg("\x1b[1;32m✅ Подключено к серверу!\x1b[0m")

	// Запускаем anti-AFK в фоне
	go d.antiAFK()

	// Ожидаем получения списка ресурс-паков (сервер пришлёт их автоматически)
	// Но мы можем явно запросить через пакет, но обычно они приходят после входа.
	// Дадим время на инициализацию
	time.Sleep(3 * time.Second)

	packs := d.conn.ResourcePacks()
	if len(packs) == 0 {
		logMsg("\x1b[1;33m⚠️ Сервер не предоставил ресурс-паки. Возможно, требуется дополнительная авторизация.\x1b[0m")
		return nil
	}

	logMsg(fmt.Sprintf("\x1b[1;36m📦 Найдено %d ресурс-паков\x1b[0m", len(packs)))

	for i, pack := range packs {
		logMsg(fmt.Sprintf("\x1b[1;34m[%d/%d] Скачивание: %s (%.2f MB)\x1b[0m",
			i+1, len(packs), pack.UUID().String(), float64(pack.Size())/1024/1024))

		// Скачиваем пак с прогресс-баром
		if err := d.downloadPack(pack); err != nil {
			logMsg(fmt.Sprintf("\x1b[1;31m❌ Ошибка скачивания: %v\x1b[0m", err))
			continue
		}
	}

	logMsg("\x1b[1;35m🏁 Все ресурс-паки успешно выкачаны!\x1b[0m")
	return nil
}

// ===========================
//  ПОДКЛЮЧЕНИЕ
// ===========================
func (d *Dumper) connect() error {
	// Формируем максимально реалистичный ClientData
	clientData := login.ClientData{
		// Основные поля
		DeviceOS:         7,                              // Windows 10/11
		DeviceModel:      "System Product Name (ASUS)",
		DeviceID:         login.DeviceID(uuid.New().String()),
		ClientRandomID:   time.Now().UnixNano(),
		GameVersion:      gameVersion,
		ServerAddress:    fmt.Sprintf("%s:%d", d.host, d.port),
		SkinID:           "Geometry_CustomSkin",
		SkinData:         "", // пусто – используем стандартный скин
		SkinImageWidth:   0,
		SkinImageHeight:  0,
		SkinResourcePatch: "",
		SkinGeometry:     "",
		SkinGeometryVersion: "",
		SkinAnimationData: "",
		SkinAnimationImageWidth: 0,
		SkinAnimationImageHeight: 0,
		CapeData:         "",
		CapeImageWidth:   0,
		CapeImageHeight:  0,
		TrustedSkin:      true,
		LanguageCode:     "ru_RU",
		// Дополнительные поля (не все поддерживаются, но добавим)
		UIProfile:        0,
		CurrentInputMode: 1,
		DefaultInputMode: 1,
		DeviceMemory:     16384,
		DeviceStorage:    512000,
		DeviceCPUCores:   8,
		DeviceCPUSpeed:   3.6,
		DeviceGPU:        "NVIDIA GeForce RTX 3060",
		DeviceGPUDriver:  "31.0.15.3742",
		ScreenWidth:      1920,
		ScreenHeight:     1080,
		ScreenDPI:        96,
	}

	dialer := minecraft.Dialer{
		ClientData:   clientData,
		TokenSource:  d.tokenSource,
		KeepAlive:    30 * time.Second,
		// Можно задать свои таймауты
		DialTimeout:  15 * time.Second,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	addr := fmt.Sprintf("%s:%d", d.host, d.port)
	conn, err := dialer.Dial("raknet", addr)
	if err != nil {
		return err
	}

	// Сохраняем соединение
	d.conn = conn
	return nil
}

// ===========================
//  СКАЧИВАНИЕ ПАКА
// ===========================
func (d *Dumper) downloadPack(pack minecraft.ResourcePack) error {
	// Используем встроенный метод DownloadResourcePack, который обрабатывает все куски
	rc, err := d.conn.DownloadResourcePack(pack)
	if err != nil {
		return err
	}
	defer rc.Close()

	// Создаём файл
	outPath := filepath.Join(outputDir, pack.UUID().String()+".zip")
	_ = os.MkdirAll(outputDir, os.ModePerm)
	f, err := os.Create(outPath)
	if err != nil {
		return err
	}
	defer f.Close()

	// Копируем с прогресс-баром (каждые 5%)
	total := pack.Size()
	var written int64
	buf := make([]byte, 1024*1024) // 1 МБ буфер
	lastPercent := -1

	for {
		n, err := rc.Read(buf)
		if n > 0 {
			_, werr := f.Write(buf[:n])
			if werr != nil {
				return werr
			}
			written += int64(n)
			percent := int((written * 100) / total)
			if percent != lastPercent && percent%5 == 0 {
				logMsg(fmt.Sprintf("\x1b[2m   ⏳ %s (%d%%)\x1b[0m", formatFileSize(written), percent))
				lastPercent = percent
			}
			// Небольшая случайная задержка, чтобы имитировать «живого» клиента
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

// ===========================
//  ANTI-AFK (ФОНОВЫЙ)
// ===========================
func (d *Dumper) antiAFK() {
	ticker := time.NewTicker(8 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			if d.conn == nil {
				return
			}
			// Генерируем случайный поворот и маленькое смещение
			yaw := rand.Float32()*360 - 180
			pitch := rand.Float32()*30 - 15
			pos := d.conn.GameData().PlayerPosition
			// Небольшое смещение
			newPos := protocol.Position{
				X: pos.X + (rand.Float32()-0.5)*0.5,
				Y: pos.Y + (rand.Float32()-0.5)*0.3,
				Z: pos.Z + (rand.Float32()-0.5)*0.5,
			}
			// Отправляем пакет движения (без телепортации)
			pk := &packet.MovePlayer{
				EntityID:   d.conn.EntityID(),
				Position:   newPos,
				Pitch:      pitch,
				Yaw:        yaw,
				HeadYaw:    yaw,
				Mode:       packet.MovePlayerModeNormal,
				OnGround:   true,
				TeleportID: 0,
			}
			if err := d.conn.WritePacket(pk); err != nil {
				// Если ошибка – возможно, соединение закрыто, выходим
				return
			}
			// Иногда делаем прыжок (5% шанс)
			if rand.Intn(20) == 0 {
				jump := &packet.PlayerAction{
					EntityID: d.conn.EntityID(),
					Action:   packet.PlayerActionJump,
				}
				_ = d.conn.WritePacket(jump)
			}
		case <-d.done:
			return
		}
	}
}

// ===========================
//  CLI ИНТЕРФЕЙС
// ===========================
func main() {
	// Инициализируем лог-файл
	_ = os.WriteFile(logFile, []byte("--- Dumper Log Start ---\n"), 0644)

	logMsg("\x1b[1;35m╔══════════════════════════════════════════════════════╗\x1b[0m")
	logMsg("\x1b[1;35m║     🛸  NeverTime RP Dumper v7.0  (Go)             ║\x1b[0m")
	logMsg("\x1b[1;35m║          Скачивание ресурс-паков с обходом         ║\x1b[0m")
	logMsg("\x1b[1;35m╚══════════════════════════════════════════════════════╝\x1b[0m")

	reader := bufio.NewReader(os.Stdin)
	fmt.Print("Введите 'packs' для начала: ")
	cmd, _ := reader.ReadString('\n')
	if strings.TrimSpace(cmd) != "packs" {
		logMsg("Выход.")
		return
	}

	fmt.Print("IP:Порт сервера (например mc.nevertime.su:19132): ")
	input, _ := reader.ReadString('\n')
	host, port := splitHostPort(strings.TrimSpace(input))

	fmt.Print("Использовать Xbox Auth? (y/n): ")
	useXbox, _ := reader.ReadString('\n')
	var tokenSrc oauth2.TokenSource

	if strings.TrimSpace(strings.ToLower(useXbox)) == "y" {
		logMsg("\x1b[1;33m⏳ Откройте ссылку в браузере и введите код.\x1b[0m")
		var err error
		tokenSrc, err = auth.RequestLiveToken()
		if err != nil {
			logMsg(fmt.Sprintf("\x1b[1;31m❌ Ошибка получения токена: %v\x1b[0m", err))
			return
		}
		logMsg("\x1b[1;32m✅ Xbox-авторизация выполнена.\x1b[0m")
	} else {
		tokenSrc = nil // офлайн-режим (не рекомендуется для NeverTime)
	}

	dumper := NewDumper(host, port, tokenSrc)
	if err := dumper.Run(); err != nil {
		logMsg(fmt.Sprintf("\x1b[1;31m❌ Критическая ошибка: %v\x1b[0m", err))
	}
}

// ===========================
//  ЗАВЕРШЕНИЕ
// ===========================
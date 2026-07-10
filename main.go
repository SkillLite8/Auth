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
	"github.com/sandertv/gophertunnel/minecraft/protocol"
	"github.com/sandertv/gophertunnel/minecraft/protocol/login"
	"github.com/sandertv/gophertunnel/minecraft/protocol/packet"
	"golang.org/x/oauth2"
)

// ===========================
//  КОНФИГУРАЦИЯ
// ===========================
const (
	outputDir   = "./resource_packs"
	logFile     = "rp_dumper.log"
	gameVersion = "1.20.30"
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
	time.Sleep(3 * time.Second)

	packs := d.conn.ResourcePacks()
	if len(packs) == 0 {
		logMsg("\x1b[1;33m⚠️ Сервер не предоставил ресурс-паки. Возможно, требуется дополнительная авторизация.\x1b[0m")
		return nil
	}

	logMsg(fmt.Sprintf("\x1b[1;36m📦 Найдено %d ресурс-паков\x1b[0m", len(packs)))

	for i, pack := range packs {
		// Получаем размер через Header()
		var size int64
		if h := pack.Header(); h != nil {
			size = int64(h.Size)
		}
		logMsg(fmt.Sprintf("\x1b[1;34m[%d/%d] Скачивание: %s (%.2f MB)\x1b[0m",
			i+1, len(packs), pack.UUID().String(), float64(size)/1024/1024))

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
	// Только проверенные поля ClientData (убираем несуществующие)
	clientData := login.ClientData{
		DeviceOS:       7,
		DeviceModel:    "System Product Name (ASUS)",
		DeviceID:       login.DeviceID(uuid.New().String()),
		ClientRandomID: time.Now().UnixNano(),
		GameVersion:    gameVersion,
		ServerAddress:  fmt.Sprintf("%s:%d", d.host, d.port),
		SkinID:         "Geometry_CustomSkin",
		SkinData:       "",
		SkinImageWidth: 0,
		SkinImageHeight: 0,
		SkinResourcePatch: "",
		SkinGeometry:   "",
		SkinGeometryVersion: "",
		SkinAnimationData: "",
		CapeData:       "",
		CapeImageWidth: 0,
		CapeImageHeight: 0,
		TrustedSkin:    true,
		LanguageCode:   "ru_RU",
		UIProfile:      0,
		CurrentInputMode: 1,
		DefaultInputMode: 1,
		// Поля DeviceMemory, DeviceStorage и т.д. удалены, так как их нет в вашей версии
	}

	dialer := minecraft.Dialer{
		ClientData:   clientData,
		TokenSource:  d.tokenSource,
		KeepAlive:    30 * time.Second,
		DialTimeout:  15 * time.Second,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	addr := fmt.Sprintf("%s:%d", d.host, d.port)
	conn, err := dialer.Dial("raknet", addr)
	if err != nil {
		return err
	}
	d.conn = conn
	return nil
}

// ===========================
//  СКАЧИВАНИЕ ПАКА (адаптировано)
// ===========================
func (d *Dumper) downloadPack(pack interface{}) error {
	// Приводим к типу, который имеет метод UUID() и Reader()
	// В старых версиях это *resource.Pack, но мы используем интерфейс
	// Для совместимости используем type assertion к известному типу
	type Pack interface {
		UUID() uuid.UUID
		Reader() io.ReadCloser
		Header() *protocol.ResourcePackHeader
	}
	p, ok := pack.(Pack)
	if !ok {
		return fmt.Errorf("неверный тип ресурс-пака")
	}

	rc := p.Reader()
	defer rc.Close()

	// Создаём файл
	_ = os.MkdirAll(outputDir, os.ModePerm)
	outPath := filepath.Join(outputDir, p.UUID().String()+".zip")
	f, err := os.Create(outPath)
	if err != nil {
		return err
	}
	defer f.Close()

	// Размер для прогресса
	var total int64
	if h := p.Header(); h != nil {
		total = int64(h.Size)
	}

	var written int64
	buf := make([]byte, 1024*1024)
	lastPercent := -1

	for {
		n, err := rc.Read(buf)
		if n > 0 {
			_, werr := f.Write(buf[:n])
			if werr != nil {
				return werr
			}
			written += int64(n)
			if total > 0 {
				percent := int((written * 100) / total)
				if percent != lastPercent && percent%5 == 0 {
					logMsg(fmt.Sprintf("\x1b[2m   ⏳ %s (%d%%)\x1b[0m", formatFileSize(written), percent))
					lastPercent = percent
				}
			}
			// Небольшая задержка
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
//  ANTI-AFK
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
			yaw := rand.Float32()*360 - 180
			pitch := rand.Float32()*30 - 15
			pos := d.conn.GameData().PlayerPosition
			newPos := protocol.Position{
				X: pos.X + (rand.Float32()-0.5)*0.5,
				Y: pos.Y + (rand.Float32()-0.5)*0.3,
				Z: pos.Z + (rand.Float32()-0.5)*0.5,
			}
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
				return
			}
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
//  CLI
// ===========================
func main() {
	rand.Seed(time.Now().UnixNano())
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
		tokenSrc = nil
	}

	dumper := NewDumper(host, port, tokenSrc)
	if err := dumper.Run(); err != nil {
		logMsg(fmt.Sprintf("\x1b[1;31m❌ Критическая ошибка: %v\x1b[0m", err))
	}
}
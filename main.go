package main

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/sandertv/gophertunnel/minecraft"
	"github.com/sandertv/gophertunnel/minecraft/protocol/login"
)

const outputDir = "./resource_packs"

func main() {
	fmt.Println("\x1b[1m\x1b[35m╔══════════════════════════════════════════════════════╗")
	fmt.Println("║     🛸  NeverTime RESOURCE PACK Dumper v5.4 (Bypass) ║")
	fmt.Println("║         Назначение: Обход защит AntiDump / BedrockTools║")
	fmt.Println("╚══════════════════════════════════════════════════════╝\x1b[0m\n")

	reader := bufio.NewReader(os.Stdin)
	fmt.Print("\x1b[32mИспользуй команду packs для начала:\x1b[0m\n> ")
	cmd, _ := reader.ReadString('\n')
	cmd = strings.TrimSpace(cmd)

	if cmd != "packs" {
		fmt.Println("❌ Неизвестная команда. Запусти программу снова.")
		return
	}

	fmt.Print("\x1b[33mEnter Server (ip:port):\x1b[0m ")
	input, _ := reader.ReadString('\n')
	input = strings.TrimSpace(input)

	host, port, err := splitHostPort(input)
	if err != nil {
		fmt.Println("❌ Неверный формат адреса. Используй ip:port")
		return
	}

	_ = os.MkdirAll(outputDir, os.ModePerm)
	fmt.Printf("🛸 Имитируем оригинальный client и подключаемся к %s:%d...\n", host, port)

	deviceId := uuid.New().String()

	clientData := login.ClientData{
		DeviceOS:         7, 
		DeviceModel:      "System Product Name (ASUS)",
		LanguageCode:     "ru_RU",
		GameVersion:      "1.20.30",
		DefaultInputMode: 1,
		CurrentInputMode: 1,
		UIProfile:        0,
		ServerAddress:    fmt.Sprintf("%s:%d", host, port),
		PlatformUserID:   uuid.New().String(),
		DeviceID:         login.DeviceID(deviceId),
		ClientRandomID:   time.Now().UnixNano(),
		SkinID:           "Geometry_CustomSkin",
		TrustedSkin:      true,
	}

	config := minecraft.Dialer{
		ClientData: clientData,
	}

	conn, err := config.Dial("raknet", fmt.Sprintf("%s:%d", host, port))
	if err != nil {
		fmt.Printf("❌ Ошибка подключения: %v\n", err)
		return
	}
	defer conn.Close()

	fmt.Println("🤝 Сетевое рукопожатие RakNet успешно!")
	fmt.Println("🕵️ Ожидаем информацию о пакетах ресурсов от сервера...")

	time.Sleep(500 * time.Millisecond)

	packs := conn.ResourcePacks()
	if len(packs) == 0 {
		fmt.Println("ℹ️ Сервер не отправил ресурс-паки.")
		return
	}

	fmt.Printf("📦 Найдено защищенных ресурс-паков: %d\n", len(packs))

	for i, pack := range packs {
		packIDStr := pack.UUID().String()
		shortID := packIDStr[:8]

		// Получаем точный размер файла пака в байтах
		packSize := pack.Len()

		fmt.Printf("   [%d/%d] -> ID: %s... | Размер: %.2f МБ\n", i+1, len(packs), shortID, float64(packSize)/1024/1024)
		
		fileName := filepath.Join(outputDir, fmt.Sprintf("%s.zip", packIDStr))
		
		fmt.Printf("📥 Начинаем безопасное скачивание для %s...\n", shortID)
		
		time.Sleep(300 * time.Millisecond)

		// Выделяем память и считываем данные напрямую
		packData := make([]byte, packSize)
		_, err := pack.ReadAt(packData, 0)
		if err != nil && err != io.EOF {
			fmt.Printf("❌ Ошибка чтения потока данных пака %s: %v\n", shortID, err)
			continue
		}
		
		// Сохраняем выгруженные байты в ZIP архив
		err = os.WriteFile(fileName, packData, 0644)
		if err != nil {
			fmt.Printf("❌ Защита сервера или ОС оборвала запись пака %s: %v\n", shortID, err)
		} else {
			fmt.Printf("💾 Пакет успешно сдамплен: %s\n", fileName)
		}
	}

	fmt.Println("🏁 Процесс завершен. Все доступные паки сохранены в папку resource_packs!")
}

func splitHostPort(input string) (string, int, error) {
	parts := strings.Split(input, ":")
	if len(parts) == 1 {
		return parts[0], 19132, nil
	}
	if len(parts) == 2 {
		port, err := strconv.Atoi(parts[1])
		if err != nil {
			return "", 0, err
		}
		return parts[0], port, nil
	}
	return "", 0, fmt.Errorf("invalid format")
}

// Beratools Launcher - launches the Python GUI application
package main

import (
	"image"
	"image/draw"
	"image/gif"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"syscall"
	"time"
	"unsafe"
)

const (
	WS_POPUP         = 0x80000000
	WS_VISIBLE       = 0x10000000
	WS_EX_TOOLWINDOW = 0x00000080
	SW_SHOW          = 5
	SM_CXSCREEN      = 0
	SM_CYSCREEN      = 1
	WM_DESTROY       = 0x0002
)

type WNDCLASSEXW struct {
	CbSize        uint32
	Style         uint32
	LpfnWndProc   uintptr
	CbClsExtra    int32
	CbWndExtra    int32
	HInstance     uintptr
	HIcon         uintptr
	HCursor       uintptr
	HbrBackground uintptr
	LpszMenuName  *uint16
	LpszClassName *uint16
	HIconSm       uintptr
}

type MSG struct {
	Hwnd    uintptr
	Message uint32
	WParam  uintptr
	LParam  uintptr
	Time    uint32
	Pt      POINT
}

type POINT struct {
	X int32
	Y int32
}

type BITMAPINFOHEADER struct {
	Size          uint32
	Width         int32
	Height        int32
	Planes        uint16
	BitCount      uint16
	Compression   uint32
	SizeImage     uint32
	XPelsPerMeter int32
	YPelsPerMeter int32
	ClrUsed       uint32
	ClrImportant  uint32
}

type RGBQUAD struct {
	Blue     byte
	Green    byte
	Red      byte
	Reserved byte
}

type BITMAPINFO struct {
	Header BITMAPINFOHEADER
	Colors [1]RGBQUAD
}

var (
	user32               = syscall.NewLazyDLL("user32.dll")
	gdi32                = syscall.NewLazyDLL("gdi32.dll")
	procRegisterClassExW = user32.NewProc("RegisterClassExW")
	procCreateWindowExW  = user32.NewProc("CreateWindowExW")
	procShowWindow       = user32.NewProc("ShowWindow")
	procUpdateWindow     = user32.NewProc("UpdateWindow")
	procDefWindowProcW   = user32.NewProc("DefWindowProcW")
	procDestroyWindow    = user32.NewProc("DestroyWindow")
	procGetSystemMetrics = user32.NewProc("GetSystemMetrics")
	procGetDC            = user32.NewProc("GetDC")
	procReleaseDC        = user32.NewProc("ReleaseDC")
	procPeekMessageW     = user32.NewProc("PeekMessageW")
	procTranslateMessage = user32.NewProc("TranslateMessage")
	procDispatchMessageW = user32.NewProc("DispatchMessageW")
	procStretchDIBits    = gdi32.NewProc("StretchDIBits")
)

func main() {
	exePath, err := os.Executable()
	if err != nil {
		os.Exit(1)
	}
	exeDir := filepath.Dir(exePath)

	// Build paths - use pythonw.exe for no console
	pythonExe := filepath.Join(exeDir, "python", "pythonw.exe")
	mainPy := filepath.Join(exeDir, "beratools", "gui", "main.py")
	splashPath := filepath.Join(exeDir, "beratools", "gui", "assets", "BERA_Splash.gif")

	readyFile := filepath.Join(os.TempDir(), "beratools_gui_ready_"+strconv.Itoa(os.Getpid())+".flag")
	_ = os.Remove(readyFile)
	done := make(chan struct{})
	go showSplash(splashPath, readyFile, done)

	// Set up environment for embedded Python
	pythonDir := filepath.Join(exeDir, "python")
	env := os.Environ()
	filteredEnv := make([]string, 0, len(env))
	for _, e := range env {
		// Remove any existing PYTHONPATH/PYTHONHOME that might interfere
		if len(e) >= 11 && e[:11] == "PYTHONPATH=" {
			continue
		}
		if len(e) >= 11 && e[:11] == "PYTHONHOME=" {
			continue
		}
		filteredEnv = append(filteredEnv, e)
	}
	// Set PYTHONPATH to include the install directory (for beratools package)
	filteredEnv = append(filteredEnv, "PYTHONPATH="+exeDir)
	filteredEnv = append(filteredEnv, "PYTHONHOME="+pythonDir)
	filteredEnv = append(filteredEnv, "BERA_SPLASH_READY="+readyFile)

	// Launch Python GUI
	cmd := exec.Command(pythonExe, mainPy)
	cmd.Dir = exeDir
	cmd.Env = filteredEnv
	if err := cmd.Start(); err != nil {
		close(done)
		os.Exit(1)
	}
	_ = cmd.Wait()
	close(done)
	_ = os.Remove(readyFile)
}

func showSplash(path string, readyFile string, done <-chan struct{}) {
	file, err := os.Open(path)
	if err != nil {
		return
	}
	defer file.Close()

	anim, err := gif.DecodeAll(file)
	if err != nil {
		return
	}

	if len(anim.Image) == 0 {
		return
	}

	runtime.LockOSThread()
	defer runtime.UnlockOSThread()

	className, _ := syscall.UTF16PtrFromString("BERAToolsSplash")
	wndClass := WNDCLASSEXW{
		CbSize:        uint32(unsafe.Sizeof(WNDCLASSEXW{})),
		LpfnWndProc:   syscall.NewCallback(wndProc),
		LpszClassName: className,
	}

	_, _, _ = procRegisterClassExW.Call(uintptr(unsafe.Pointer(&wndClass)))

	bounds := anim.Image[0].Bounds()
	width := bounds.Dx()
	height := bounds.Dy()
	screenW, _, _ := procGetSystemMetrics.Call(SM_CXSCREEN)
	screenH, _, _ := procGetSystemMetrics.Call(SM_CYSCREEN)
	x := int32(int32(screenW)/2 - int32(width)/2)
	y := int32(int32(screenH)/2 - int32(height)/2)

	hwnd, _, _ := procCreateWindowExW.Call(
		WS_EX_TOOLWINDOW,
		uintptr(unsafe.Pointer(className)),
		uintptr(unsafe.Pointer(className)),
		WS_POPUP|WS_VISIBLE,
		uintptr(x),
		uintptr(y),
		uintptr(width),
		uintptr(height),
		0,
		0,
		0,
		0,
	)
	if hwnd == 0 {
		return
	}

	procShowWindow.Call(hwnd, SW_SHOW)
	procUpdateWindow.Call(hwnd)

	canvas := image.NewRGBA(bounds)
	var msg MSG
	for i := 0; ; i = (i + 1) % len(anim.Image) {
		if shouldCloseSplash(readyFile, done) {
			break
		}

		frame := anim.Image[i]
		composed := image.NewRGBA(bounds)
		draw.Draw(composed, bounds, canvas, image.Point{}, draw.Src)
		draw.Draw(composed, frame.Bounds(), frame, frame.Bounds().Min, draw.Over)
		canvas = composed
		drawSplash(hwnd, composed)

		delay := anim.Delay[i]
		if delay <= 0 {
			delay = 10
		}
		waitUntil := time.Now().Add(time.Duration(delay) * 10 * time.Millisecond)
		for time.Now().Before(waitUntil) {
			if shouldCloseSplash(readyFile, done) {
				procDestroyWindow.Call(hwnd)
				return
			}
			for {
				ret, _, _ := procPeekMessageW.Call(uintptr(unsafe.Pointer(&msg)), 0, 0, 0, 1)
				if ret == 0 {
					break
				}
				if msg.Message == WM_DESTROY {
					return
				}
				procTranslateMessage.Call(uintptr(unsafe.Pointer(&msg)))
				procDispatchMessageW.Call(uintptr(unsafe.Pointer(&msg)))
			}
			time.Sleep(15 * time.Millisecond)
		}
	}

	procDestroyWindow.Call(hwnd)
}

func shouldCloseSplash(readyFile string, done <-chan struct{}) bool {
	select {
	case <-done:
		return true
	default:
	}
	if readyFile == "" {
		return false
	}
	_, err := os.Stat(readyFile)
	return err == nil
}

func drawSplash(hwnd uintptr, img *image.RGBA) {
	hdc, _, _ := procGetDC.Call(hwnd)
	if hdc == 0 {
		return
	}
	defer procReleaseDC.Call(hwnd, hdc)

	width := img.Bounds().Dx()
	height := img.Bounds().Dy()

	bgra := rgbaToBGRA(img.Pix)

	bmi := BITMAPINFO{
		Header: BITMAPINFOHEADER{
			Size:     uint32(unsafe.Sizeof(BITMAPINFOHEADER{})),
			Width:    int32(width),
			Height:   -int32(height),
			Planes:   1,
			BitCount: 32,
		},
	}

	procStretchDIBits.Call(
		hdc,
		0,
		0,
		uintptr(width),
		uintptr(height),
		0,
		0,
		uintptr(width),
		uintptr(height),
		uintptr(unsafe.Pointer(&bgra[0])),
		uintptr(unsafe.Pointer(&bmi)),
		0,
		0x00CC0020,
	)
}

func rgbaToBGRA(src []byte) []byte {
	if len(src) == 0 {
		return src
	}
	dst := make([]byte, len(src))
	for i := 0; i+3 < len(src); i += 4 {
		dst[i] = src[i+2]
		dst[i+1] = src[i+1]
		dst[i+2] = src[i]
		dst[i+3] = src[i+3]
	}
	return dst
}

func wndProc(hwnd uintptr, msg uint32, wparam, lparam uintptr) uintptr {
	switch msg {
	case WM_DESTROY:
		return 0
	}
	ret, _, _ := procDefWindowProcW.Call(hwnd, uintptr(msg), wparam, lparam)
	return ret
}

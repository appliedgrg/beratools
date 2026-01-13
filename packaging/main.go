// Beratools Launcher - launches the Python GUI application
package main

import (
	"os"
	"os/exec"
	"path/filepath"
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

	// Launch Python GUI
	cmd := exec.Command(pythonExe, mainPy)
	cmd.Dir = exeDir
	cmd.Env = filteredEnv
	_ = cmd.Run()
}

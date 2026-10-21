package desktop

import (
	"embed"
	"encoding/json"
	"fmt"
)

//go:embed locales/*.json
var localeFiles embed.FS

var catalogs = func() map[string]map[string]string {
	result := map[string]map[string]string{}
	for _, language := range []string{"en", "zh-CN"} {
		b, err := localeFiles.ReadFile("locales/" + language + ".json")
		if err != nil {
			panic(err)
		}
		var terms map[string]string
		if err := json.Unmarshal(b, &terms); err != nil {
			panic(err)
		}
		result[language] = terms
	}
	return result
}()

func validLanguage(language string) bool { return language == "en" || language == "zh-CN" }
func normalizedLanguage(language string) string {
	if language == "zh-CN" {
		return language
	}
	return "en"
}

// Catalogs returns a copy of the built-in application text. No locale detection
// or external translation service is involved; raw logs are never translated.
func Catalogs() map[string]map[string]string {
	result := map[string]map[string]string{}
	for lang, terms := range catalogs {
		copy := map[string]string{}
		for key, value := range terms {
			copy[key] = value
		}
		result[lang] = copy
	}
	return result
}
func Text(language, key string) string {
	if value, ok := catalogs[normalizedLanguage(language)][key]; ok {
		return value
	}
	return catalogs["en"]["error.generic"]
}
func (c *Controller) Language() string {
	c.mu.Lock()
	defer c.mu.Unlock()
	return normalizedLanguage(c.prefs.Language)
}
func (c *Controller) text(key string) string { return Text(c.Language(), key) }

// SetLanguage persists only GUI preferences. It never changes the VM, data root
// or installation identity, and shares prefMu with every other preference write.
func (c *Controller) SetLanguage(language string) (Status, error) {
	if !validLanguage(language) {
		return c.GetStatus(), fmt.Errorf("unsupported GUI language: %s", language)
	}
	c.prefMu.Lock()
	defer c.prefMu.Unlock()
	c.mu.Lock()
	p := c.prefs
	p.Version = preferencesVersion
	p.DataRoot = c.dataRoot
	p.Language = language
	blocked := c.prefBlocked
	path := c.prefsPath
	c.mu.Unlock()
	if blocked || path == "" {
		return c.GetStatus(), fmt.Errorf("launcher preferences are unavailable; language was not saved")
	}
	if err := savePreferences(path, p); err != nil {
		return c.GetStatus(), err
	}
	c.mu.Lock()
	c.prefs = p
	c.status.Language = language
	c.publishLocked()
	st := c.status
	c.mu.Unlock()
	return st, nil
}

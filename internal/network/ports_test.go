package network

import "testing"

func TestOriginMatchesBrowserDefaultPortNormalization(t *testing.T) {
	for port, expected := range map[int]string{80: "http://127.0.0.1", 8080: "http://127.0.0.1:8080", 7171: "http://127.0.0.1:7171"} {
		if got := Origin(port); got != expected {
			t.Fatalf("port %d: %s, want %s", port, got, expected)
		}
	}
}

func TestPortsAcceptFormerServiceRange(t *testing.T) {
	for _, value := range []string{"1", "80", "17871", "17891", "17954", "65535"} {
		if _, err := ParsePort(value); err != nil {
			t.Fatal(value, err)
		}
	}
	for _, value := range []string{"", "abc", "0", "-1", "65536", "7172", "999999999999999999999999999999"} {
		if _, err := ParsePort(value); err == nil {
			t.Fatal("invalid port accepted:", value)
		}
	}
}

package platform

import "errors"

var ErrLocked = errors.New("another instance owns this installation or disk")

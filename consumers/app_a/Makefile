# Standalone consumer: only main.c and an installed SDK prefix are needed.
SDK_PREFIX ?=
ifeq ($(strip $(SDK_PREFIX)),)
$(error SDK_PREFIX must identify an installed SDK)
endif
PKG_CONFIG ?= pkg-config
PC_ENV = PKG_CONFIG_PATH="$(SDK_PREFIX)/lib/pkgconfig" PKG_CONFIG_LIBDIR="$(SDK_PREFIX)/lib/pkgconfig"
SDK_CFLAGS = $(shell $(PC_ENV) $(PKG_CONFIG) --cflags madlink)
SDK_LIBS = $(shell $(PC_ENV) $(PKG_CONFIG) --libs madlink)
.PHONY: all test check-sdk FORCE
all: consumer
check-sdk:
	$(PC_ENV) $(PKG_CONFIG) --exists madlink
main.o: main.c | check-sdk
	$(CC) -std=c11 -Wall -Wextra -Wpedantic -Werror $(CFLAGS) $(SDK_CFLAGS) -MMD -MF main.d -c main.c -o main.o
consumer: main.o FORCE
	$(CXX) $(LDFLAGS) main.o $(SDK_LIBS) -o consumer
test: consumer
	./consumer
FORCE:
-include main.d

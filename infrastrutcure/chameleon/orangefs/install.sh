#! /usr/bin/env bash

set -e

PKGNAM=orangefs
VERSION="2.10.1"
OFSURL="https://github.com/waltligon/orangefs/releases/download/2.10.1/orangefs-2.10.1.tar.gz"

wget $OFSURL
tar zxvf ${PKGNAM}-${VERSION}.tar.gz
cd ${PKGNAM}

./prepare
./configure --prefix=/opt/${PKGNAM}/${VERSION}/ --enable-shared --with-db-backend=lmdb --enable-fast --enable-threaded-kmod-helper
make
make install
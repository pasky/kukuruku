all: modes c2s_pb2.py

.PHONY: modes clean

modes:
	$(MAKE) -C modes

c2s_pb2.py:
	protoc -I=../server/ --python_out=. ../server/c2s.proto

clean:
	$(MAKE) -C modes clean
	rm c2s_pb2.py c2s_pb2.pyc


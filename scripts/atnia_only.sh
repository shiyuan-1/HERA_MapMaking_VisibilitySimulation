#! /bin/bash



Q=$1
for f in `echo 0 5 10`; do
	echo '========================================================================='
	echo python map_making_dynamic_unpolarized_fast_cholesky.py miteor ${Q}_${f}_abscal atnia10428
	python map_making_dynamic_unpolarized_fast_cholesky.py miteor ${Q}_${f}_abscal atnia10428
	echo '-------------------------------------------------------------------------'
done;

#f=$1
#echo '========================================================================='
#echo python map_making_dynamic_unpolarized_fast_cholesky.py paper psa128_epoch2_${f} atnia14896
#python map_making_dynamic_unpolarized_fast_cholesky.py paper psa128_epoch2_${f} atnia14896
#echo '-------------------------------------------------------------------------'






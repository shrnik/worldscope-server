#SBATCH -o download%j.out
#SBATCH -e download%j.err

# single node in the "short" partition
#SBATCH -N 1
#SBATCH -p gpu

#SBATCH --mail-user=s.borad@gwu.edu
#SBATCH --mail-type=ALL
#SBATCH --gres=gpu:1

# half hour timelimit
#SBATCH -t 7:00:00:00

module load python3/3.12.9_sqlite

source ~/visor/.venv/bin/activate

python ./worldscope-server/python/embedding_worker.py
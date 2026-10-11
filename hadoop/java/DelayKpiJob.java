import java.io.DataInput;
import java.io.DataOutput;
import java.io.IOException;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.conf.Configured;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.io.Writable;
import org.apache.hadoop.mapreduce.Job;
import org.apache.hadoop.mapreduce.Mapper;
import org.apache.hadoop.mapreduce.Reducer;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;
import org.apache.hadoop.util.Tool;
import org.apache.hadoop.util.ToolRunner;

/**
 * Native Java MapReduce version of the delivery-KPI job (for comparison with Hadoop Streaming).
 *
 * Usage: hadoop jar delaylens-mr.jar DelayKpiJob -D delaylens.key.col=16 <in> <out>
 * key.col indexes the cleaned order-item TSV (16 = order_region, 8 = shipping_mode, 20 = category).
 * Output: key \t items \t late \t late_pct \t avg_delay_days
 */
public class DelayKpiJob extends Configured implements Tool {

    /** Partial aggregate: count, late count and summed delay; associative so it works as a combiner. */
    public static class KpiWritable implements Writable {
        long count;
        long late;
        double delaySum;

        public KpiWritable() { }

        KpiWritable(long count, long late, double delaySum) {
            this.count = count;
            this.late = late;
            this.delaySum = delaySum;
        }

        @Override
        public void write(DataOutput out) throws IOException {
            out.writeLong(count);
            out.writeLong(late);
            out.writeDouble(delaySum);
        }

        @Override
        public void readFields(DataInput in) throws IOException {
            count = in.readLong();
            late = in.readLong();
            delaySum = in.readDouble();
        }
    }

    public static class KpiMapper extends Mapper<LongWritable, Text, Text, KpiWritable> {
        private final Text outKey = new Text();
        private int keyCol;

        @Override
        protected void setup(Context ctx) {
            keyCol = ctx.getConfiguration().getInt("delaylens.key.col", 16);
        }

        @Override
        protected void map(LongWritable offset, Text line, Context ctx) throws IOException, InterruptedException {
            String[] f = line.toString().split("\t", -1);
            if (f.length < 30) {
                ctx.getCounter("DelayLens", "MalformedLines").increment(1);
                return;
            }
            outKey.set(f[keyCol]);
            long late = "Late delivery".equals(f[12]) ? 1 : 0;
            ctx.write(outKey, new KpiWritable(1, late, Double.parseDouble(f[11])));
        }
    }

    public static class KpiCombiner extends Reducer<Text, KpiWritable, Text, KpiWritable> {
        @Override
        protected void reduce(Text key, Iterable<KpiWritable> vals, Context ctx) throws IOException, InterruptedException {
            KpiWritable acc = new KpiWritable(0, 0, 0);
            for (KpiWritable v : vals) {
                acc.count += v.count;
                acc.late += v.late;
                acc.delaySum += v.delaySum;
            }
            ctx.write(key, acc);
        }
    }

    public static class KpiReducer extends Reducer<Text, KpiWritable, Text, Text> {
        @Override
        protected void reduce(Text key, Iterable<KpiWritable> vals, Context ctx) throws IOException, InterruptedException {
            long count = 0, late = 0;
            double delay = 0;
            for (KpiWritable v : vals) {
                count += v.count;
                late += v.late;
                delay += v.delaySum;
            }
            ctx.write(key, new Text(count + "\t" + late + "\t"
                    + String.format("%.2f", 100.0 * late / count) + "\t"
                    + String.format("%.3f", delay / count)));
        }
    }

    @Override
    public int run(String[] args) throws Exception {
        Configuration conf = getConf();
        Job job = Job.getInstance(conf, "delaylens-java-kpi-col" + conf.getInt("delaylens.key.col", 16));
        job.setJarByClass(DelayKpiJob.class);
        job.setMapperClass(KpiMapper.class);
        job.setCombinerClass(KpiCombiner.class);
        job.setReducerClass(KpiReducer.class);
        job.setMapOutputKeyClass(Text.class);
        job.setMapOutputValueClass(KpiWritable.class);
        job.setOutputKeyClass(Text.class);
        job.setOutputValueClass(Text.class);
        FileInputFormat.addInputPath(job, new Path(args[0]));
        FileOutputFormat.setOutputPath(job, new Path(args[1]));
        return job.waitForCompletion(true) ? 0 : 1;
    }

    public static void main(String[] args) throws Exception {
        System.exit(ToolRunner.run(new DelayKpiJob(), args));
    }
}
